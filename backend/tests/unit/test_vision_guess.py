from activities import vision_guess


def test_returns_stub_output_matching_expected_shape():
    result = vision_guess.run({"image_blob_url": "https://example.com/photo.jpg"})

    assert set(result.keys()) == {"dish_name_guess", "cuisine_guess", "elements"}
    assert isinstance(result["dish_name_guess"], str) and result["dish_name_guess"]
    assert isinstance(result["cuisine_guess"], str) and result["cuisine_guess"]
    assert len(result["elements"]) > 0
    for element in result["elements"]:
        assert set(element.keys()) == {"name", "description", "confidence"}


def test_confidence_values_are_bounded_0_to_1():
    result = vision_guess.run({"image_blob_url": "https://example.com/another.jpg"})

    for element in result["elements"]:
        assert 0.0 <= element["confidence"] <= 1.0


def test_deterministic_for_same_input():
    first = vision_guess.run({"image_blob_url": "https://example.com/same.jpg"})
    second = vision_guess.run({"image_blob_url": "https://example.com/same.jpg"})

    assert first == second
