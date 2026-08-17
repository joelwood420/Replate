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
                "price": item.get("price"),
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
    last_error: Exception | None = None

    logging.info("Fetching menu for %s via web_search", name)

    for _ in range(config.menu_fetch_max_retries() + 1):
        try:
            raw = anthropic_client.web_search_completion(
                model, messages, system=_SYSTEM_PROMPT
            )
        except anthropic_client.AnthropicError as exc:
            # A model error is not retryable here - a missing key or a denied
            # model will fail identically every time.
            raise MenuExtractionError(
                f"Anthropic error fetching menu for {name}: {exc}"
            ) from exc

        try:
            return _validate(anthropic_client.parse_json_response(raw))
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            # Show the model its own bad output rather than just asking again -
            # a blind retry tends to reproduce the same mistake.
            messages = messages + [
                {"role": "assistant", "content": [{"type": "text", "text": raw}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "That wasn't valid JSON matching the schema. Respond with ONLY the JSON object."}
                    ],
                },
            ]
            continue

    raise MenuExtractionError(f"Failed to parse menu for {name} after retries: {last_error}") from last_error
