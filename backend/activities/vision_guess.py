"""Preliminary vision guess: break the uploaded dish photo into visible elements.

Was a canned stub that hash-picked one of three fixed dishes. Now sends the
uploaded photo to Claude (first-party Anthropic API) and asks for a structured
breakdown - a dish-name guess, a cuisine guess, and each visible element with a
short description and a presence confidence.

This is a *guess*, on purpose. The pipeline cross-checks it against the
restaurant's real fetched menu in match_menu_item (the anti-hallucination spine),
so this call is prompted to give its best visual read rather than to be
authoritative - a wrong name here is corrected downstream by the menu match. It is
the frequent, at-the-table stage-1 call, so it runs at low effort on a mid-tier
model (claude-sonnet-5).

A blank ANTHROPIC_VISION_MODEL (or missing key) degrades to the canned stub,
matching generate_recreation's posture - local runs and the smoke test work
without model spend.
"""

import base64
import copy
import hashlib

from shared import anthropic_client, config, storage

# Anthropic accepts these image media types; anything else (or a missing
# ContentType on the S3 object) falls back to JPEG, which the uploads are.
_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_DEFAULT_IMAGE_TYPE = "image/jpeg"

_SYSTEM = (
    "You are a chef and food photographer analysing a photo. First decide whether the "
    "photo actually shows a food or drink dish. If it does not (for example a person, a "
    "pet, a landscape, a screenshot, or an empty plate), set is_food to false, write a "
    "short friendly not_food_reason, and leave the dish fields empty. If it does show a "
    "dish, set is_food to true, identify it, and break it into the components a diner can "
    "actually see on the plate. This is a preliminary visual read that will be cross-checked "
    "against the restaurant's real menu, so give your best guess from the image alone and do "
    "not invent components you cannot see. For each element give a short visual description "
    "and a confidence from 0 to 1 that it is present."
)

_USER_TEXT = (
    "Is this a photo of a food or drink dish? If not, say so with is_food false and a short "
    "not_food_reason. If it is, return a dish-name guess, a cuisine guess, and each visible "
    "component with a short description and a 0-1 presence confidence."
)

# Shown to the user (as the job's error_message) when the photo is not a dish and the model
# did not supply its own reason. Kept light: a wrong photo is a mistake, not a failure.
_NOT_FOOD_MESSAGE = (
    "Our chef squinted at that one and could not find any food. "
    "Try again with a photo of your plate."
)

# Structured-output schema. Mirrors the stub's shape exactly, because match_menu_item
# reads `dish_name_guess`, each element's `description`, and averages the per-element
# `confidence` into the vision confidence - so the contract is fixed by that consumer.
_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["is_food", "not_food_reason", "dish_name_guess", "cuisine_guess", "elements"],
    "properties": {
        "is_food": {"type": "boolean"},
        "not_food_reason": {"type": "string"},
        "dish_name_guess": {"type": "string"},
        "cuisine_guess": {"type": "string"},
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "description", "confidence"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
}


# ---- Stub fallback (no model configured) -------------------------------------
# Preserves the pre-Phase-3b canned behaviour so the pipeline still completes
# end-to-end locally / in the smoke test without any model spend.

CANNED_GUESSES = [
    {
        "dish_name_guess": "Margherita Pizza",
        "cuisine_guess": "Italian",
        "elements": [
            {"name": "Pizza crust", "description": "Thin, charred wood-fired crust", "confidence": 0.82},
            {"name": "Tomato sauce", "description": "Simple crushed tomato sauce", "confidence": 0.78},
            {"name": "Mozzarella", "description": "Fresh mozzarella, melted", "confidence": 0.88},
            {"name": "Basil", "description": "Fresh basil leaves", "confidence": 0.70},
        ],
    },
    {
        "dish_name_guess": "Pad Thai",
        "cuisine_guess": "Thai",
        "elements": [
            {"name": "Rice noodles", "description": "Stir-fried flat rice noodles", "confidence": 0.80},
            {"name": "Tamarind sauce", "description": "Sweet-sour tamarind glaze", "confidence": 0.65},
            {"name": "Peanuts", "description": "Crushed roasted peanuts garnish", "confidence": 0.75},
            {"name": "Egg", "description": "Scrambled egg mixed through", "confidence": 0.60},
        ],
    },
    {
        "dish_name_guess": "Cheeseburger",
        "cuisine_guess": "American",
        "elements": [
            {"name": "Beef patty", "description": "Grilled ground beef patty", "confidence": 0.90},
            {"name": "Cheese", "description": "Melted cheddar slice", "confidence": 0.85},
            {"name": "Bun", "description": "Toasted brioche bun", "confidence": 0.77},
            {"name": "Lettuce & tomato", "description": "Fresh lettuce and tomato slice", "confidence": 0.60},
        ],
    },
]


def _stub(image_key: str) -> dict:
    digest = hashlib.sha256(image_key.encode("utf-8")).digest()
    index = digest[0] % len(CANNED_GUESSES)
    guess = copy.deepcopy(CANNED_GUESSES[index])
    # The canned samples are always dishes, so the stub never trips the food gate.
    guess["is_food"] = True
    guess["not_food_reason"] = None
    return guess


def _image_block(image_key: str) -> dict:
    """The uploaded photo as a base64 image content block for the Messages API."""
    data, content_type = storage.read_object(image_key)
    media_type = content_type if content_type in _SUPPORTED_IMAGE_TYPES else _DEFAULT_IMAGE_TYPE
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


def _normalize(data: dict) -> dict:
    """Coerce the model output to the fixed shape and clamp confidences to 0-1.

    match_menu_item averages the per-element confidence, so a stray out-of-range
    value from the model must not skew it; missing names/descriptions get safe
    defaults so a partial element never breaks the match step. When the model says
    the photo is not food, guarantee a user-facing reason: the state machine shows
    not_food_reason to the user, so it must never be blank.
    """
    is_food = bool(data.get("is_food", True))
    reason = (data.get("not_food_reason") or "").strip()
    if not is_food and not reason:
        reason = _NOT_FOOD_MESSAGE

    elements = []
    for element in data.get("elements") or []:
        try:
            confidence = float(element.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        elements.append(
            {
                "name": element.get("name") or "Component",
                "description": element.get("description") or "",
                "confidence": round(confidence, 4),
            }
        )
    return {
        "is_food": is_food,
        "not_food_reason": reason or None,
        "dish_name_guess": data.get("dish_name_guess") or "",
        "cuisine_guess": data.get("cuisine_guess") or "",
        "elements": elements,
    }


def run(activity_input: dict) -> dict:
    image_key = activity_input.get("image_key") or ""

    model = config.anthropic_vision_model()
    if not (model and anthropic_client.is_configured()):
        return _stub(image_key)

    data = anthropic_client.generate_structured(
        model=model,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                # Image before text, so the model reads the photo then the task.
                "content": [_image_block(image_key), {"type": "text", "text": _USER_TEXT}],
            }
        ],
        schema=_RESULT_SCHEMA,
        max_tokens=2048,
        # A visual breakdown is perception + light structuring, not hard reasoning;
        # low effort keeps this frequent stage-1 call cheap and fast.
        effort="low",
    )
    return _normalize(data)


def handler(event, context=None):
    """Lambda entry point for the VisionGuess task in statemachines/dish-identify.asl.json."""
    return run(event)
