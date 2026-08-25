"""Match the vision model's dish guess against the restaurant's real menu.

This is the anti-hallucination step: a real menu item's name is trusted over the vision
model's unaided guess. The match is done by an in-context LLM classifier - it is given the
vision guess plus the one restaurant's menu and picks the single best item or "none", which
handles stylised/shortened names ("The Classic Benny" == "Eggs Benedict") that a character
similarity misses. The model may only choose a listed item or none, never invent one, so the
anti-hallucination property holds.

The older `difflib` character-similarity matcher is kept as a fallback for when the model is
not configured (stub deploy) or a call fails, so the step always produces one of the three
confidence outcomes and never fails the job.
"""

import difflib
import logging

from shared import anthropic_client, config
from shared.models import MatchMethod

_MATCH_SYSTEM = (
    "You match a diner's photographed dish to one restaurant's real menu. Choose the single "
    "menu item that best matches the dish, or none if no listed item is a plausible match. "
    "Only ever choose from the numbered menu items provided - never invent a dish. Match on "
    'meaning, not spelling: a stylised or shortened name ("The Classic Benny") can be the '
    'same dish as its menu name ("Eggs Benedict").'
)

_MATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["match_index", "confidence"],
    "properties": {
        # 0-based index into the menu list, or -1 for "no plausible match".
        "match_index": {"type": "integer"},
        # 0..1 confidence that match_index is the diner's dish.
        "confidence": {"type": "number"},
    },
}


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _score_menu_item(vision_guess: dict, menu_item: dict) -> float:
    dish_name_guess = vision_guess.get("dish_name_guess", "")
    element_descriptions = " ".join(e.get("description", "") for e in vision_guess.get("elements", []))
    candidate_text = f"{menu_item.get('item_name', '')} {menu_item.get('item_description', '')}"

    name_score = _similarity(dish_name_guess, menu_item.get("item_name", ""))
    desc_score = _similarity(element_descriptions, menu_item.get("item_description", ""))
    combined_score = _similarity(dish_name_guess, candidate_text)
    return max(name_score, desc_score, combined_score)


def _vision_confidence(vision_guess: dict) -> float:
    elements = vision_guess.get("elements") or []
    if not elements:
        return 0.0
    scores = [e.get("confidence", 0.0) for e in elements]
    return round(sum(scores) / len(scores), 4)


def _difflib_match(vision_guess: dict, menu_items: list[dict]) -> tuple[int, float]:
    """Character-similarity fallback: return (best index, score), or (-1, 0.0) if none."""
    best_index = -1
    best_score = 0.0
    for index, item in enumerate(menu_items):
        score = _score_menu_item(vision_guess, item)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index, round(best_score, 4)


def _menu_lines(menu_items: list[dict]) -> str:
    lines = []
    for index, item in enumerate(menu_items):
        description = item.get("item_description") or ""
        suffix = f" - {description}" if description else ""
        lines.append(f"{index}. {item.get('item_name', '')}{suffix}")
    return "\n".join(lines)


def _classify_with_llm(vision_guess: dict, menu_items: list[dict]) -> tuple[int, float] | None:
    """Ask the model to pick the best menu item (or none).

    Returns (index, confidence) - index -1 means "no plausible match" - or None if the model
    is not configured or the call failed, signalling the caller to fall back to difflib. An
    out-of-range index (a model slip) is coerced to "none" so it can never point off the menu.
    """
    if not anthropic_client.is_configured():
        return None
    model = config.anthropic_match_model()
    if not model:
        return None

    dish = vision_guess.get("dish_name_guess") or "(unknown)"
    cuisine = vision_guess.get("cuisine_guess") or "(unknown)"
    components = "; ".join(
        f"{e.get('name', '')}: {e.get('description', '')}".strip(": ")
        for e in vision_guess.get("elements", [])
    )
    prompt = (
        "Diner's dish (from a photo):\n"
        f"- best-guess name: {dish}\n"
        f"- cuisine: {cuisine}\n"
        f"- visible components: {components or '(none noted)'}\n\n"
        f"Restaurant menu:\n{_menu_lines(menu_items)}\n\n"
        "Return the index of the single best-matching menu item, or -1 if none is a plausible "
        "match, with your confidence 0-1."
    )

    try:
        data = anthropic_client.generate_structured(
            model=model,
            system=_MATCH_SYSTEM,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            schema=_MATCH_SCHEMA,
            max_tokens=256,
            effort="low",
        )
    except anthropic_client.AnthropicError as exc:
        logging.info("Menu-match LLM call failed, falling back to difflib: %s", exc)
        return None

    try:
        index = int(data["match_index"])
        confidence = float(data["confidence"])
    except (KeyError, TypeError, ValueError):
        return None
    if index < 0 or index >= len(menu_items):
        return -1, 0.0
    return index, round(confidence, 4)


def run(activity_input: dict) -> dict:
    vision_guess = activity_input["vision_guess"]
    menu_items = activity_input.get("menu_items") or []
    candidate_found = activity_input.get("candidate_found", False)
    restaurant_id = activity_input.get("restaurant_id")

    dish_name = vision_guess.get("dish_name_guess")
    cuisine = vision_guess.get("cuisine_guess")
    vision_confidence = _vision_confidence(vision_guess)

    if not candidate_found:
        return {
            "matched_restaurant_id": None,
            "matched_menu_item_id": None,
            "match_confidence": 0.0,
            "match_method": MatchMethod.VISION_ONLY_LOW,
            "dish_name": dish_name,
            "cuisine": cuisine,
            "vision_confidence": vision_confidence,
        }

    threshold = config.menu_match_confidence_threshold()

    # LLM classifier first; difflib is the fallback when it is unavailable. With no menu there
    # is nothing to classify, so skip straight to the vision-only medium outcome.
    match = _classify_with_llm(vision_guess, menu_items) if menu_items else (-1, 0.0)
    if match is None:
        match = _difflib_match(vision_guess, menu_items)
    index, confidence = match

    if 0 <= index < len(menu_items) and confidence >= threshold:
        best_item = menu_items[index]
        return {
            "matched_restaurant_id": restaurant_id,
            "matched_menu_item_id": best_item.get("menu_item_id"),
            "match_confidence": round(confidence, 4),
            "match_method": MatchMethod.MENU_MATCHED,
            "dish_name": best_item.get("item_name", dish_name),
            "cuisine": cuisine,
            "vision_confidence": vision_confidence,
        }

    return {
        "matched_restaurant_id": restaurant_id,
        "matched_menu_item_id": None,
        "match_confidence": round(confidence, 4),
        "match_method": MatchMethod.VISION_ONLY_MEDIUM,
        "dish_name": dish_name,
        "cuisine": cuisine,
        "vision_confidence": vision_confidence,
    }


def handler(event, context=None):
    """Lambda entry point for the MatchMenuItem task in statemachines/dish-identify.asl.json."""
    return run(event)
