from activities import generate_recreation


def test_output_shape_matches_dish_elements_ingredients_steps_tables(sample_vision_guess):
    result = generate_recreation.run({"vision_guess": sample_vision_guess, "embeddings_context": []})

    assert set(result.keys()) == {"elements"}
    for index, element in enumerate(result["elements"], start=1):
        assert set(element.keys()) == {"name", "description", "role", "sort_order", "ingredients", "steps"}
        assert element["sort_order"] == index
        assert element["role"] == generate_recreation._STUB_ROLES[(index - 1) % len(generate_recreation._STUB_ROLES)]
        for ingredient in element["ingredients"]:
            assert set(ingredient.keys()) == {"ingredient_name", "amount", "unit", "sort_order"}
        for step in element["steps"]:
            assert set(step.keys()) == {"step_number", "instruction"}


def test_includes_matched_menu_item_context_when_present(sample_vision_guess):
    embeddings_context = [{"embedding_id": "e1", "source_text": "Blooming spices", "cuisine_type": "Indian", "distance": 0.1}]

    result = generate_recreation.run(
        {"vision_guess": sample_vision_guess, "embeddings_context": embeddings_context}
    )

    all_instructions = " ".join(
        step["instruction"] for element in result["elements"] for step in element["steps"]
    )
    assert "Blooming spices" in all_instructions


def test_falls_back_to_vision_only_context_when_no_match(sample_vision_guess):
    result = generate_recreation.run({"vision_guess": sample_vision_guess, "embeddings_context": []})

    assert len(result["elements"]) == len(sample_vision_guess["elements"])


def test_prompt_includes_full_menu_description_when_menu_matched(sample_vision_guess):
    """The menu description (components the short title omits) must reach the model."""
    matched_menu_item = {
        "dish_name": "Sicilian stuffed squid & crispy tentacles",
        "dish_description": "cannellini beans & preserved lemon",
        "match_method": "menu_matched",
    }

    prompt = generate_recreation._prompt(matched_menu_item, sample_vision_guess, [])

    assert "Sicilian stuffed squid & crispy tentacles" in prompt
    assert "cannellini beans & preserved lemon" in prompt


def test_prompt_omits_menu_description_line_when_absent(sample_vision_guess):
    """Vision-only outcomes have no menu description, so no such line is added."""
    matched_menu_item = {"dish_name": "Margherita Pizza", "dish_description": None, "match_method": "vision_only_medium"}

    prompt = generate_recreation._prompt(matched_menu_item, sample_vision_guess, [])

    assert "Menu description:" not in prompt
