import azure.durable_functions as df

bp = df.Blueprint()


def _stub_ingredients(element_name: str) -> list[dict]:
    return [
        {"ingredient_name": f"{element_name} base ingredient", "amount": "1", "unit": "cup", "sort_order": 1},
        {"ingredient_name": "Salt", "amount": "1", "unit": "tsp", "sort_order": 2},
        {"ingredient_name": "Olive oil", "amount": "2", "unit": "tbsp", "sort_order": 3},
    ]


def _stub_steps(element_name: str, technique_hint: str | None) -> list[dict]:
    steps = [
        {"step_number": 1, "instruction": f"Prepare the {element_name.lower()} ingredients."},
        {"step_number": 2, "instruction": f"Cook the {element_name.lower()} until done to your taste."},
    ]
    if technique_hint:
        steps.append({"step_number": 3, "instruction": f"Finish using this technique: {technique_hint}"})
    return steps


def run(activity_input: dict) -> dict:
    vision_guess = activity_input.get("vision_guess") or {}
    embeddings_context = activity_input.get("embeddings_context") or []

    elements_source = vision_guess.get("elements") or []
    technique_hint = embeddings_context[0]["source_text"] if embeddings_context else None

    elements = []
    for index, element in enumerate(elements_source, start=1):
        name = element.get("name", f"Component {index}")
        elements.append(
            {
                "name": name,
                "description": element.get("description", ""),
                "sort_order": index,
                "ingredients": _stub_ingredients(name),
                "steps": _stub_steps(name, technique_hint),
            }
        )

    return {"elements": elements}


@bp.activity_trigger(input_name="activityInput")
def generate_recreation(activityInput: dict) -> dict:
    return run(activityInput)
