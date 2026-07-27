import json

from anthropic import Anthropic, APIConnectionError, APIStatusError, APITimeoutError

from shared import config

_PROMPT_TEMPLATE = """Search the web for the current menu of "{name}"{address_clause}.
Respond with ONLY a JSON object of this exact shape, no prose before or after:
{{"items": [{{"item_name": "...", "item_description": "...", "price": "..." or null}}]}}
If you cannot find a menu, respond with {{"items": []}}."""


class MenuExtractionError(Exception):
    pass


def _parse_response(response) -> list[dict]:
    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise ValueError("no text content in Claude response")

    raw = text_blocks[-1].strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    data = json.loads(raw)
    items = data.get("items")
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
    client = Anthropic(api_key=config.anthropic_api_key(), timeout=config.menu_fetch_timeout_seconds())
    address_clause = f" at {address}" if address else ""
    prompt = _PROMPT_TEMPLATE.format(name=name, address_clause=address_clause)
    if menu_source_url:
        prompt += f"\nA known menu source URL: {menu_source_url}"

    messages: list[dict] = [{"role": "user", "content": prompt}]
    last_error: Exception | None = None

    for _ in range(config.menu_fetch_max_retries() + 1):
        try:
            response = client.messages.create(
                model=config.menu_fetch_model(),
                max_tokens=4096,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
                messages=messages,
            )
        except (APIConnectionError, APITimeoutError) as exc:
            last_error = exc
            continue
        except APIStatusError as exc:
            raise MenuExtractionError(f"Claude API error fetching menu for {name}: {exc}") from exc

        if response.stop_reason == "pause_turn":
            # Server-tool loop hit its internal iteration limit; resume by
            # re-sending the paused assistant turn - the API detects the
            # trailing server_tool_use block and continues automatically.
            messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": response.content}]
            continue

        try:
            return _parse_response(response)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": "That wasn't valid JSON matching the schema. Respond with ONLY the JSON object.",
                },
            ]
            continue

    raise MenuExtractionError(f"Failed to fetch menu for {name} after retries: {last_error}") from last_error
