import difflib


from shared import config
from shared.models import MatchMethod


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
    best_item = None
    best_score = 0.0
    for item in menu_items:
        score = _score_menu_item(vision_guess, item)
        if score > best_score:
            best_score = score
            best_item = item

    if best_item is not None and best_score >= threshold:
        return {
            "matched_restaurant_id": restaurant_id,
            "matched_menu_item_id": best_item.get("menu_item_id"),
            "match_confidence": round(best_score, 4),
            "match_method": MatchMethod.MENU_MATCHED,
            "dish_name": best_item.get("item_name", dish_name),
            "cuisine": cuisine,
            "vision_confidence": vision_confidence,
        }

    return {
        "matched_restaurant_id": restaurant_id,
        "matched_menu_item_id": None,
        "match_confidence": round(best_score, 4),
        "match_method": MatchMethod.VISION_ONLY_MEDIUM,
        "dish_name": dish_name,
        "cuisine": cuisine,
        "vision_confidence": vision_confidence,
    }


def handler(event, context=None):
    """Lambda entry point for the MatchMenuItem task in statemachines/dish-identify.asl.json."""
    return run(event)
