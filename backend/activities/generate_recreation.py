"""Generate a per-element method to recreate an identified dish.

Was a canned stub. Now calls Claude (first-party Anthropic API) to produce, for
each visible element of the dish, an ingredient list and an ordered method -
grounded in the matched menu item's real name (when stage 1 found one), the
vision model's visual breakdown, and the retrieved culinary-technique snippets.

This is the heaviest-output, most expensive call in the pipeline (see
statemachines/dish-recipe.asl.json), so `max_tokens` and effort are set
deliberately and generation is rate-limited upstream.

A blank ANTHROPIC_GENERATOR_MODEL (or missing key) degrades to the canned stub,
matching the vision_guess / menu-fetch stub posture - local runs and the smoke
test work without model spend.
"""

from shared import anthropic_client, config


# The `role` the model may assign an element. Kept as an enum in the schema so
# the value is always one the frontend's grouping/labelling can rely on.
_ROLE_ENUM = ["Protein", "Sauce", "Side", "Garnish", "Base", "Dessert", "Component"]

_SYSTEM = (
    "You are a chef reverse-engineering a restaurant dish so a competent home cook "
    "can recreate it. Work element by element. Ground every ingredient and step in "
    "what is actually visible or named - do not invent components that are not part "
    "of the dish. Quantities are for a single serving, and should be real amounts a "
    "cook can measure. Techniques should be specific and practical."
)

# Structured-output schema. sort_order / step_number are assigned in Python
# (see _normalize) rather than asked of the model, so ordering is always correct
# and dense regardless of what the model emits.
_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["elements"],
    "properties": {
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "description", "role", "ingredients", "steps"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "role": {"type": "string", "enum": _ROLE_ENUM},
                    "ingredients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["ingredient_name", "amount", "unit"],
                            "properties": {
                                "ingredient_name": {"type": "string"},
                                "amount": {"type": "string"},
                                "unit": {"type": "string"},
                            },
                        },
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["instruction"],
                            "properties": {"instruction": {"type": "string"}},
                        },
                    },
                },
            },
        }
    },
}


def _prompt(matched_menu_item: dict, vision_guess: dict, embeddings_context: list[dict]) -> str:
    """Assemble the user message from the three grounding sources."""
    dish_name = matched_menu_item.get("dish_name") or vision_guess.get("dish_name_guess") or "this dish"
    # The menu item's description carries components the short title omits (e.g.
    # "cannellini beans & preserved lemon"); it is only set on a menu match and is
    # never shown on the page, but it must reach the model so those elements are
    # actually recreated.
    dish_description = matched_menu_item.get("dish_description")
    cuisine = vision_guess.get("cuisine_guess")
    elements = vision_guess.get("elements") or []
    techniques = [e.get("source_text") for e in (embeddings_context or []) if e.get("source_text")]

    lines = [f"Dish: {dish_name}"]
    if dish_description:
        lines.append(f"Menu description: {dish_description}")
    if cuisine:
        lines.append(f"Cuisine: {cuisine}")
    if matched_menu_item.get("match_method") == "menu_matched":
        if dish_description:
            lines.append(
                "This name and menu description come from the restaurant's actual menu - trust "
                "them over any guess, and make sure every component they name (including each one "
                "in the description) appears as its own element in your recreation."
            )
        else:
            lines.append("This name comes from the restaurant's actual menu - trust it over any guess.")

    lines.append("")
    lines.append("Visible elements identified from the photo:")
    for element in elements:
        lines.append(f"- {element.get('name', 'Component')}: {element.get('description', '')}")

    if techniques:
        lines.append("")
        lines.append("Relevant culinary techniques to draw on:")
        for technique in techniques[:5]:
            lines.append(f"- {technique}")

    lines.append("")
    lines.append(
        "For each element, give its ingredients (single serving) and an ordered list of "
        "method steps. Keep elements aligned with the visible components above."
    )
    return "\n".join(lines)


def _normalize(raw_elements: list[dict]) -> dict:
    """Assign dense sort orders / step numbers and coerce to the persisted shape.

    `repository.replace_dish_elements` requires element `sort_order`, ingredient
    `sort_order`, and step `step_number`; the model isn't asked for those, so we
    number them here.
    """
    elements = []
    for index, element in enumerate(raw_elements, start=1):
        ingredients = [
            {
                "ingredient_name": ingredient.get("ingredient_name", ""),
                "amount": ingredient.get("amount"),
                "unit": ingredient.get("unit"),
                "sort_order": position,
            }
            for position, ingredient in enumerate(element.get("ingredients") or [], start=1)
        ]
        steps = [
            {"step_number": number, "instruction": step.get("instruction", "")}
            for number, step in enumerate(element.get("steps") or [], start=1)
        ]
        elements.append(
            {
                "name": element.get("name", f"Component {index}"),
                "description": element.get("description", ""),
                "role": element.get("role") or "Component",
                "sort_order": index,
                "ingredients": ingredients,
                "steps": steps,
            }
        )
    return {"elements": elements}


# ---- Stub fallback (no model configured) -------------------------------------
# Preserves the pre-Phase-3b canned behaviour so the pipeline still completes
# end-to-end locally / in the smoke test without any model spend.

_STUB_ROLES = ["Protein", "Sauce", "Side", "Garnish", "Component"]


def _stub(vision_guess: dict, embeddings_context: list[dict]) -> dict:
    technique_hint = embeddings_context[0]["source_text"] if embeddings_context else None
    raw = []
    for element in vision_guess.get("elements") or []:
        name = element.get("name", "Component")
        steps = [
            {"instruction": f"Prepare the {name.lower()} ingredients."},
            {"instruction": f"Cook the {name.lower()} until done to your taste."},
        ]
        if technique_hint:
            steps.append({"instruction": f"Finish using this technique: {technique_hint}"})
        raw.append(
            {
                "name": name,
                "description": element.get("description", ""),
                "role": _STUB_ROLES[len(raw) % len(_STUB_ROLES)],
                "ingredients": [
                    {"ingredient_name": f"{name} base ingredient", "amount": "1", "unit": "cup"},
                    {"ingredient_name": "Salt", "amount": "1", "unit": "tsp"},
                    {"ingredient_name": "Olive oil", "amount": "2", "unit": "tbsp"},
                ],
                "steps": steps,
            }
        )
    return _normalize(raw)


def run(activity_input: dict) -> dict:
    matched_menu_item = activity_input.get("matched_menu_item") or {}
    vision_guess = activity_input.get("vision_guess") or {}
    embeddings_context = activity_input.get("embeddings_context") or []

    # TEMP diagnostic logging - pinpoints where a hang occurs (SSM read vs model
    # call). Remove once the timeout root cause is fixed.
    model = config.anthropic_generator_model()
    if not (model and anthropic_client.is_configured()):
        return _stub(vision_guess, embeddings_context)

    data = anthropic_client.generate_structured(
        model=model,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt(matched_menu_item, vision_guess, embeddings_context)}
                ],
            }
        ],
        schema=_RESULT_SCHEMA,
        max_tokens=4096,
        # Structured recipe generation is knowledge + formatting, not hard
        # reasoning; low effort keeps latency well under the Lambda timeout (the
        # medium default was overrunning 120s) and trims cost on this, the
        # pipeline's most expensive call.
        effort="low",
    )
    return _normalize(data.get("elements") or [])


def handler(event, context=None):
    """Lambda entry point for the GenerateRecreation task in statemachines/dish-recipe.asl.json."""
    return run(event)
