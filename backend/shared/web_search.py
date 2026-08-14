"""Finding and fetching a restaurant's menu page.

This module exists because of the Bedrock decision. Anthropic's first-party API
has a server-side `web_search` tool, and `fetch_restaurant_menu` was built on it -
one call did search, fetch and extract. Bedrock does not expose that tool, so the
step splits into three, and the first two live here.

The split is not purely a loss. Each stage is independently testable and
mockable, the search provider is swappable behind `SERP_API_ENDPOINT`, and the
per-call cost is visible per stage rather than hidden inside one opaque
tool-using call.

Defaults target the Brave Search API, which has a free monthly allowance. The
response parser is deliberately lenient about shape so pointing
`SERP_API_ENDPOINT` at a different provider is a config change plus, at most, a
small edit to `_extract_results`.
"""

import html
import logging
import re

import httpx

from shared import config


class SearchError(Exception):
    """Search or fetch failed. Callers degrade rather than fail the job."""


def is_configured() -> bool:
    return bool(config.serp_api_key())


def _extract_results(payload: dict) -> list[dict]:
    """Pull {title, url} out of a SERP response.

    Brave nests results under `web.results`; several other providers use a
    top-level `organic_results` or `results`. Checking all three keeps the
    provider swap to a config change in the common case.
    """
    for path in (("web", "results"), ("organic_results",), ("results",)):
        node = payload
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, list):
            return [
                {"title": entry.get("title", ""), "url": entry.get("url") or entry.get("link", "")}
                for entry in node
                if entry.get("url") or entry.get("link")
            ]
    return []


def search(query: str) -> list[dict]:
    """Run a web search. Returns `[{"title": ..., "url": ...}]`, nearest match first."""
    if not is_configured():
        raise SearchError("SERP_API_KEY is not set")

    try:
        response = httpx.get(
            config.serp_api_endpoint(),
            params={"q": query, "count": config.serp_max_results()},
            headers={
                "X-Subscription-Token": config.serp_api_key(),
                "Accept": "application/json",
            },
            timeout=config.serp_timeout_seconds(),
        )
    except httpx.HTTPError as exc:
        raise SearchError(f"search request failed: {type(exc).__name__}: {exc}") from exc

    if response.status_code >= 400:
        raise SearchError(f"search returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchError(f"unparseable search response: {exc}") from exc

    return _extract_results(payload)[: config.serp_max_results()]


_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def html_to_text(markup: str) -> str:
    """Strip a page down to readable text.

    Deliberately regex rather than a parser dependency. The output only has to be
    good enough for a model to read menu items out of - it is not a rendering
    engine, and adding BeautifulSoup to the Lambda layer for this would be a poor
    trade. Scripts and styles go first, because their contents are not markup and
    would otherwise survive tag-stripping as noise.
    """
    text = _SCRIPT_STYLE.sub(" ", markup)
    text = _TAG.sub("\n", text)
    text = html.unescape(text)
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_LINES.sub("\n\n", text).strip()


def fetch_page_text(url: str) -> str:
    """Fetch a page and return its visible text, truncated to a budget.

    The truncation is a cost control, not a nicety: an unbounded page goes
    straight into a model prompt, so one restaurant with a huge embedded script
    could otherwise cost more than the rest of the day's traffic.
    """
    try:
        response = httpx.get(
            url,
            timeout=config.page_fetch_timeout_seconds(),
            follow_redirects=True,
            headers={"User-Agent": "ReplateBot/1.0 (+menu extraction)"},
        )
    except httpx.HTTPError as exc:
        raise SearchError(f"page fetch failed for {url}: {type(exc).__name__}: {exc}") from exc

    if response.status_code >= 400:
        raise SearchError(f"page fetch for {url} returned HTTP {response.status_code}")

    text = html_to_text(response.text)
    limit = config.page_fetch_max_chars()
    if len(text) > limit:
        logging.info("Truncating %s from %d to %d chars", url, len(text), limit)
        text = text[:limit]
    return text


def find_menu_page(name: str, address: str | None, menu_source_url: str | None) -> tuple[str, str]:
    """Locate a menu page and return `(url, page_text)`.

    A known `menu_source_url` is tried first and skips the search entirely - one
    fewer billable call, and a known-good URL beats a search result. If it fails
    the search still runs, because a stale cached URL should not permanently break
    menu fetching for that restaurant.
    """
    if menu_source_url:
        try:
            return menu_source_url, fetch_page_text(menu_source_url)
        except SearchError as exc:
            logging.info("Known menu URL %s failed (%s), falling back to search", menu_source_url, exc)

    where = f" {address}" if address else ""
    results = search(f"{name}{where} menu")
    if not results:
        raise SearchError(f"no search results for {name}")

    last_error: Exception | None = None
    for result in results:
        try:
            return result["url"], fetch_page_text(result["url"])
        except SearchError as exc:
            last_error = exc
            continue

    raise SearchError(f"every candidate page failed for {name}: {last_error}")
