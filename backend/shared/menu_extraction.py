"""Turn a restaurant's menu page into structured menu items.

Was a single Claude call using Anthropic's server-side `web_search` tool, which
did search, fetch and extract in one. Bedrock does not expose that tool, so this
is now the third stage of search -> fetch -> extract; the first two are in
`shared/web_search.py`.

The extraction prompt itself barely changed - it was already "turn this into
structured menu items". What changed is that the page text arrives as an argument
rather than being gathered by the model, which means the model no longer needs a
tool loop, a `pause_turn` resume path, or five search iterations of budget.
"""

import json
import logging

from shared import bedrock, config, web_search

_SYSTEM_PROMPT = (
    "You extract restaurant menu items from web page text. "
    "Respond with ONLY a JSON object, no prose before or after."
)

_PROMPT_TEMPLATE = """Extract the menu items for "{name}"{address_clause} from the page text below.

Respond with ONLY a JSON object of this exact shape:
{{"items": [{{"item_name": "...", "item_description": "...", "price": "..." or null}}]}}

Rules:
- Only include actual food and drink items. Ignore navigation, opening hours,
  addresses, allergen keys and marketing copy.
- If the page is not a menu, or you cannot find any items, respond with {{"items": []}}.

Page URL: {url}

Page text:
{page_text}"""


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


def extract_from_page(name: str, address: str | None, url: str, page_text: str) -> list[dict]:
    """Ask the model to structure one page's text. Retries on unparseable output."""
    address_clause = f" at {address}" if address else ""
    prompt = _PROMPT_TEMPLATE.format(
        name=name, address_clause=address_clause, url=url, page_text=page_text
    )

    messages = [{"role": "user", "content": [{"text": prompt}]}]
    last_error: Exception | None = None

    for _ in range(config.menu_fetch_max_retries() + 1):
        try:
            raw = bedrock.converse(
                config.bedrock_menu_model_id(), messages, system=_SYSTEM_PROMPT
            )
        except bedrock.BedrockError as exc:
            # A model error is not retryable here - a missing model id or a denied
            # model grant will fail identically every time.
            raise MenuExtractionError(f"Bedrock error fetching menu for {name}: {exc}") from exc

        try:
            return _validate(bedrock.parse_json_response(raw))
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            # Show the model its own bad output rather than just asking again -
            # a blind retry at temperature 0 tends to reproduce the same mistake.
            messages = messages + [
                {"role": "assistant", "content": [{"text": raw}]},
                {
                    "role": "user",
                    "content": [
                        {"text": "That wasn't valid JSON matching the schema. Respond with ONLY the JSON object."}
                    ],
                },
            ]
            continue

    raise MenuExtractionError(f"Failed to parse menu for {name} after retries: {last_error}") from last_error


def fetch_menu_items(name: str, address: str | None, menu_source_url: str | None) -> list[dict]:
    """Find, fetch and extract a restaurant's menu.

    Signature and return shape are unchanged from the Anthropic version, so
    `activities/fetch_restaurant_menu.py` and its graceful-degrade path did not
    have to change - a MenuExtractionError still means "no real menu data", which
    the match step already handles as the vision-only medium-confidence outcome.
    """
    if not config.bedrock_menu_model_id():
        raise MenuExtractionError(
            f"Cannot fetch menu for {name}: BEDROCK_MENU_MODEL_ID is not set"
        )

    try:
        url, page_text = web_search.find_menu_page(name, address, menu_source_url)
    except web_search.SearchError as exc:
        raise MenuExtractionError(f"Could not find a menu page for {name}: {exc}") from exc

    if not page_text.strip():
        raise MenuExtractionError(f"Menu page for {name} at {url} had no readable text")

    logging.info("Extracting menu for %s from %s (%d chars)", name, url, len(page_text))
    return extract_from_page(name, address, url, page_text)
