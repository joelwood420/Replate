"""Find a restaurant's menu and turn it into structured menu items.

One Claude call using the first-party API's server-side `web_search` tool does
search, fetch and extract together (docs/decisions.md, 2026-08-17). This was the
original design; the Bedrock era split it into search -> fetch -> extract because
Bedrock did not expose the tool. Moving back to the first-party API restores the
single call and removes shared/web_search.py.

The extraction contract - a JSON object of menu items - is unchanged, so the
retry-on-unparseable-output behaviour and `activities/fetch_restaurant_menu.py`'s
graceful degrade did not have to change.
"""

import json
import logging

from shared import anthropic_client, config

_SYSTEM_PROMPT = (
    "You find and extract restaurant menu items. Use the web_search tool to find "
    "the restaurant's menu, then respond with ONLY a JSON object, no prose before "
    "or after."
)

_PROMPT_TEMPLATE = """Find the current menu for "{name}"{address_clause} and extract its items.

Search the web for this restaurant's menu, read the most relevant page, then
respond with ONLY a JSON object of this exact shape:
{{"items": [{{"item_name": "...", "item_description": "..." or "", "price": "..." or null}}]}}

Rules:
- Only include actual food and drink items. Ignore navigation, opening hours,
  addresses, allergen keys and marketing copy.
- If you cannot find a menu for this restaurant, respond with {{"items": []}}."""

# The reformat pass never searches - it only reshapes text the web_search call
# already gathered - so it can use structured outputs (a server tool cannot),
# which guarantees schema-valid JSON in one cheap turn.
_REFORMAT_SYSTEM = (
    "You reshape restaurant menu text that has already been gathered into structured "
    "data. Do not search the web. Include only real food and drink items; ignore "
    "navigation, hours, addresses and marketing copy."
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
                # An empty price string (how the reformat schema signals "unknown")
                # normalizes to None, matching the web_search path's null price.
                "price": item.get("price") or None,
            }
        )
    return validated


def fetch_menu_items(name: str, address: str | None, menu_source_url: str | None) -> list[dict]:
    """Find, fetch and extract a restaurant's menu in one web_search call.

    Signature and return shape are unchanged from the Bedrock version, so
    `activities/fetch_restaurant_menu.py` and its graceful-degrade path did not
    have to change - a MenuExtractionError still means "no real menu data", which
    the match step already handles as the vision-only medium-confidence outcome.
    `menu_source_url` is accepted for signature compatibility; the model does its
    own searching, so a hint URL is folded into the prompt rather than fetched
    here.
    """
    if not anthropic_client.is_configured():
        raise MenuExtractionError(
            f"Cannot fetch menu for {name}: ANTHROPIC_API_KEY is not set"
        )

    model = config.anthropic_menu_model()
    if not model:
        raise MenuExtractionError(
            f"Cannot fetch menu for {name}: ANTHROPIC_MENU_MODEL is not set"
        )

    address_clause = f" at {address}" if address else ""
    prompt = _PROMPT_TEMPLATE.format(name=name, address_clause=address_clause)
    if menu_source_url:
        prompt += f"\n\nA known menu page for this restaurant is: {menu_source_url}"

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

    logging.info("Fetching menu for %s via web_search", name)

    # The one paid web_search sweep: find, read and extract in a single call.
    try:
        raw = anthropic_client.web_search_completion(model, messages, system=_SYSTEM_PROMPT)
    except anthropic_client.AnthropicError as exc:
        # A model error is not retryable here - a missing key or a denied model
        # will fail identically every time.
        raise MenuExtractionError(f"Anthropic error fetching menu for {name}: {exc}") from exc

    try:
        return _validate(anthropic_client.parse_json_response(raw))
    except (ValueError, json.JSONDecodeError):
        # The web_search output was not clean JSON (citations, prose, a stray
        # fence). The model already found and read the menu, so re-running
        # web_search would just re-bill the whole sweep - that path once cost 15
        # searches for a single dish. Instead reshape its own output with a cheap,
        # tool-free structured call that cannot search and cannot return invalid JSON.
        logging.info("Menu JSON for %s needed a reformat pass (no re-search)", name)

    return _reformat_menu_text(model, name, raw)


def _reformat_menu_text(model: str, name: str, raw: str) -> list[dict]:
    """Coerce already-gathered menu text into the schema, without searching again."""
    try:
        data = anthropic_client.generate_structured(
            model=model,
            system=_REFORMAT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract the menu items from the text below into the "
                                "required JSON schema. Use an empty string for a missing "
                                f"description or price.\n\n{raw}"
                            ),
                        }
                    ],
                }
            ],
            schema=_MENU_SCHEMA,
            max_tokens=2048,
            effort="low",
        )
    except anthropic_client.AnthropicError as exc:
        raise MenuExtractionError(f"Could not reformat menu for {name}: {exc}") from exc

    try:
        return _validate(data)
    except (ValueError, json.JSONDecodeError) as exc:
        raise MenuExtractionError(f"Failed to parse menu for {name}: {exc}") from exc
