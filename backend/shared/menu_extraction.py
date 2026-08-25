"""Find a restaurant's menu and turn it into structured menu items.

Deterministic pipeline (docs/decisions.md): SerpApi finds the menu-page URL from the
restaurant name + address, `page_fetch` fetches that one page (HTML, PDF or image), and one
cheap tool-free Claude structured-extract call reshapes it into menu items. This replaces the
first-party `web_search` sweep, which was location-blind and kept searching until its budget
was exhausted - it timed out at 120s and cost dollars per session (the 2026-08-24 incident).

The whole step is bounded by `config.menu_fetch_budget_seconds()`. A genuine "no menu online"
result returns an empty list (a *success*, so the activity caches it and does not re-burn a
SerpApi search next scan); a transient failure - a SerpApi/model error, or the budget running
out mid-flight - raises MenuExtractionError, which the caller degrades to the vision-only
outcome and which leaves the cache untouched so the next job retries.

The extraction contract - a JSON object of menu items - is unchanged, so the signature,
`_MENU_SCHEMA`, `_validate` and `activities/fetch_restaurant_menu.py`'s graceful degrade did
not have to change.
"""

import base64
import json
import logging
import time

from shared import anthropic_client, config, page_fetch, secrets, serpapi

_EXTRACT_SYSTEM = (
    "You reshape a single restaurant's menu - given as page text, a PDF, or an image - into "
    "structured data. Do not invent items. Include only real food and drink items; ignore "
    "navigation, opening hours, addresses, allergen keys and marketing copy."
)

_EXTRACT_INSTRUCTION = (
    "Extract the menu items from this restaurant menu into the required JSON schema. Use an "
    "empty string for a missing description or price. If it contains no menu items, return "
    '{"items": []}.'
)

_MENU_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_name", "item_description", "price"],
                "properties": {
                    "item_name": {"type": "string"},
                    # Empty string, not null, for a missing description or price -
                    # structured outputs are simplest with a single concrete type;
                    # _validate maps an empty price back to None.
                    "item_description": {"type": "string"},
                    "price": {"type": "string"},
                },
            },
        },
    },
}


class MenuExtractionError(Exception):
    pass


def _validate(payload: dict) -> list[dict]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("response JSON missing 'items' list")

    validated = []
    for item in items:
        if not isinstance(item, dict) or not item.get("item_name"):
            raise ValueError(f"invalid menu item: {item!r}")
        validated.append(
            {
                "item_name": item["item_name"],
                "item_description": item.get("item_description") or "",
                # An empty price string (how the schema signals "unknown") normalizes to None.
                "price": item.get("price") or None,
            }
        )
    return validated


def _resolved_serpapi_key() -> str:
    """The SerpApi key, from SSM when deployed or the env var locally.

    Mirrors `anthropic_client._resolved_key`: an SSM failure degrades to the no-key path
    (which surfaces as a MenuExtractionError -> the vision-only outcome) rather than crashing.
    """
    param = config.serpapi_key_param()
    if param:
        try:
            return secrets.get_secure_parameter(param)
        except Exception as exc:  # noqa: BLE001 - degrade on any SSM failure
            logging.warning("Could not read %s from SSM: %s", param, exc)
            return ""
    return config.serpapi_key()


def _discover_menu_url(name, address, menu_source_url, api_key, timeout) -> tuple[str | None, bool]:
    """Find the best menu URL, falling back to the OSM website hint.

    Returns (url, must_retry). `must_retry` is True when there is no URL and the reason is
    transient/config - a SerpApi error or a missing key - so the caller can retry (raise)
    rather than cache an empty result. A clean search that simply found nothing returns
    (None, False), a genuine "no menu online" the caller may cache.
    """
    serp_url = None
    serp_errored = False
    if api_key:
        try:
            serp_url = serpapi.find_menu_url(name, address, api_key, timeout)
        except serpapi.SerpApiError as exc:
            logging.info("SerpApi failed for %s, falling back to any known URL: %s", name, exc)
            serp_errored = True
    else:
        logging.info("No SerpApi key configured; using the OSM URL hint for %s if present", name)

    url = serp_url or menu_source_url
    # must_retry: only when we have no URL AND the reason is transient/config, not a clean
    # "SerpApi searched and found nothing". A SerpApi error or a missing key with no fallback
    # should be retried on the next job (raise, don't cache); a genuine empty search caches [].
    # A usable fallback URL makes both moot.
    must_retry = url is None and (serp_errored or not api_key)
    return url, must_retry


def fetch_menu_items(name: str, address: str | None, menu_source_url: str | None) -> list[dict]:
    """Find, fetch and extract a restaurant's menu, bounded by the menu-fetch budget.

    Signature and return shape are unchanged from the web_search version. An empty list is a
    successful "no menu online" answer (the activity caches it); a MenuExtractionError is a
    transient/config failure the caller degrades to the vision-only medium-confidence outcome.
    """
    if not anthropic_client.is_configured():
        raise MenuExtractionError(f"Cannot fetch menu for {name}: ANTHROPIC_API_KEY is not set")

    model = config.anthropic_menu_model()
    if not model:
        raise MenuExtractionError(f"Cannot fetch menu for {name}: ANTHROPIC_MENU_MODEL is not set")

    deadline = time.monotonic() + config.menu_fetch_budget_seconds()

    def remaining() -> float:
        return deadline - time.monotonic()

    # 1. Discover the menu URL (SerpApi, with the OSM website as a fallback hint).
    serp_timeout = min(config.serpapi_timeout_seconds(), max(remaining(), 0.0))
    url, must_retry = _discover_menu_url(
        name, address, menu_source_url, _resolved_serpapi_key(), serp_timeout
    )
    if url is None:
        if must_retry:
            # SerpApi errored, or no key was configured, with no fallback URL - a transient/
            # config state. Raise so the next job retries rather than caching an empty menu.
            raise MenuExtractionError(f"Could not discover a menu URL for {name}")
        logging.info("No menu URL found for %s; treating as no menu online", name)
        return []

    # 2. Fetch that one page. A None here (unknown type, empty, oversize) is a genuine "no menu
    #    at this URL" - return [] so the activity caches it. A transport error raises
    #    PageFetchError instead, which we turn into a MenuExtractionError so a one-off network
    #    blip is not cached as a permanent no-menu for the full TTL.
    if remaining() <= 0:
        raise MenuExtractionError(f"Menu fetch for {name} ran out of budget before fetching")
    page_timeout = min(config.page_fetch_timeout_seconds(), remaining())
    try:
        content = page_fetch.fetch_menu_content(url, page_timeout)
    except page_fetch.PageFetchError as exc:
        raise MenuExtractionError(f"Menu page fetch failed for {name}: {exc}") from exc
    if content is None:
        logging.info("Menu URL %s for %s yielded no usable content", url, name)
        return []

    # 3. Extract the page we fetched, giving it the full remaining budget so nothing can starve
    #    it. Many restaurant "menu" pages are an HTML shell with no dishes of their own that just
    #    link to PDF menus, so only when the page itself yields nothing do we follow those PDFs.
    if remaining() <= 0:
        raise MenuExtractionError(f"Menu fetch for {name} ran out of budget before extracting")

    pdf_links = content.get("pdf_links") or []
    # Skip a pointless extract of an HTML shell with no text of its own and go straight to its
    # PDFs. A directly-fetched PDF/image, or an HTML page with real text, is extracted first.
    if content["kind"] != "html" or content.get("text"):
        logging.info("Extracting menu for %s from %s (%s)", name, url, content["kind"])
        items = _extract_content(model, name, content, timeout=remaining())
        if items:
            return items
    if not pdf_links:
        return []

    pdf_items, had_transient_failure = _follow_pdf_menus(model, name, pdf_links, deadline)
    if pdf_items:
        return pdf_items
    if had_transient_failure:
        # Every linked PDF failed transiently (a fetch or model error), not "genuinely empty".
        # Raise so the caller retries next job rather than caching a false "no menu" for the TTL
        # - the same raise-don't-cache contract the primary page fetch above upholds.
        raise MenuExtractionError(f"All linked PDF menus for {name} failed to fetch or extract")
    return []


# Need enough of the budget left for a PDF fetch plus its extract before following another one.
_PDF_FOLLOW_MIN_BUDGET = 5.0


def _extract_content(model: str, name: str, content: dict, timeout: float) -> list[dict]:
    """One cheap, tool-free structured extract of already-fetched content (html/pdf/image).

    `timeout` bounds the call by what is left of the menu-fetch budget so a slow extract
    degrades here rather than getting the Lambda killed.
    """
    try:
        data = anthropic_client.generate_structured(
            model=model,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": _build_content(content)}],
            schema=_MENU_SCHEMA,
            max_tokens=2048,
            effort="low",
            timeout=timeout,
        )
    except anthropic_client.AnthropicError as exc:
        raise MenuExtractionError(f"Anthropic error extracting menu for {name}: {exc}") from exc

    try:
        return _validate(data)
    except (ValueError, json.JSONDecodeError) as exc:
        raise MenuExtractionError(f"Failed to parse menu for {name}: {exc}") from exc


def _follow_pdf_menus(
    model: str, name: str, pdf_links: list[str], deadline: float
) -> tuple[list[dict], bool]:
    """Fetch and extract up to `menu_pdf_max_follow` linked PDF menus, merging their items.

    Returns (items, had_transient_failure). Bounded by the shared deadline and the follow cap.
    Items are de-duplicated by name so overlapping menus (a food PDF and a set menu) do not
    double up. A PDF that fails to *fetch* or *extract* transiently (a network or model error,
    as opposed to genuinely containing no items) is skipped but flips `had_transient_failure`,
    so the caller can raise-and-retry rather than cache a false "no menu" when nothing else
    yields a menu either.
    """
    def remaining() -> float:
        return deadline - time.monotonic()

    items: list[dict] = []
    seen: set[str] = set()
    followed = 0
    had_transient_failure = False
    for link in pdf_links:
        if followed >= config.menu_pdf_max_follow() or remaining() <= _PDF_FOLLOW_MIN_BUDGET:
            break
        try:
            pdf = page_fetch.fetch_menu_content(link, min(config.page_fetch_timeout_seconds(), remaining()))
        except page_fetch.PageFetchError as exc:
            logging.info("Could not fetch linked PDF %s for %s: %s", link, name, exc)
            had_transient_failure = True
            continue
        if not pdf or pdf["kind"] != "pdf":
            # A link that resolved to something that is not a usable PDF - a bad link, not a
            # transient blip, so it does not force a retry.
            continue
        followed += 1
        if remaining() <= 0:
            break
        try:
            extracted = _extract_content(model, name, pdf, timeout=remaining())
        except MenuExtractionError as exc:
            logging.info("Linked PDF %s for %s did not extract: %s", link, name, exc)
            had_transient_failure = True
            continue
        for item in extracted:
            key = item["item_name"].strip().lower()
            if key not in seen:
                seen.add(key)
                items.append(item)

    if items:
        logging.info("Extracted %d menu items for %s from %d linked PDF(s)", len(items), name, followed)
    return items, had_transient_failure


def _build_content(content: dict) -> list[dict]:
    """Turn a `page_fetch` result into Messages API content blocks for the extract call.

    HTML becomes a text block; a PDF or image becomes a document/image block (Claude reads
    both natively) followed by the instruction text. Document/image blocks go before the text
    block per the Messages API guidance.
    """
    if content["kind"] == "html":
        return [{"type": "text", "text": f"{_EXTRACT_INSTRUCTION}\n\n{content['text']}"}]

    encoded = base64.standard_b64encode(content["data"]).decode("ascii")
    if content["kind"] == "pdf":
        block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": encoded},
        }
    else:  # image
        block = {
            "type": "image",
            "source": {"type": "base64", "media_type": content["media_type"], "data": encoded},
        }
    return [block, {"type": "text", "text": _EXTRACT_INSTRUCTION}]
