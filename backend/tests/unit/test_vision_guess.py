from activities import vision_guess
from shared import anthropic_client, config, storage


def test_returns_stub_output_matching_expected_shape():
    result = vision_guess.run({"image_key": "https://example.com/photo.jpg"})

    assert set(result.keys()) == {
        "is_food",
        "not_food_reason",
        "dish_name_guess",
        "cuisine_guess",
        "elements",
    }
    # The canned samples are always dishes, so the stub never trips the food gate.
    assert result["is_food"] is True
    assert result["not_food_reason"] is None
    assert isinstance(result["dish_name_guess"], str) and result["dish_name_guess"]
    assert isinstance(result["cuisine_guess"], str) and result["cuisine_guess"]
    assert len(result["elements"]) > 0
    for element in result["elements"]:
        assert set(element.keys()) == {"name", "description", "confidence"}


def test_confidence_values_are_bounded_0_to_1():
    result = vision_guess.run({"image_key": "https://example.com/another.jpg"})

    for element in result["elements"]:
        assert 0.0 <= element["confidence"] <= 1.0


def test_deterministic_for_same_input():
    first = vision_guess.run({"image_key": "https://example.com/same.jpg"})
    second = vision_guess.run({"image_key": "https://example.com/same.jpg"})

    assert first == second


def test_calls_model_with_image_and_normalizes_when_configured(monkeypatch):
    """With a model + key configured, the photo is sent as an image block and the
    result is coerced to the fixed shape with confidences clamped to 0-1."""
    captured = {}
    monkeypatch.setattr(config, "anthropic_vision_model", lambda: "claude-sonnet-5-5")
    monkeypatch.setattr(anthropic_client, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "read_object", lambda key: (b"\xff\xd8fakejpeg", "image/jpeg"))

    def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return {
            "dish_name_guess": "Raspberry Mille-Feuille",
            "cuisine_guess": "French",
            # 1.5 is out of range on purpose - _normalize must clamp it to 1.0.
            "elements": [{"name": "Kataifi crown", "description": "crisp pastry", "confidence": 1.5}],
        }

    monkeypatch.setattr(anthropic_client, "generate_structured", fake_generate_structured)

    result = vision_guess.run({"image_key": "uploads/x.jpg"})

    content = captured["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["type"] == "base64"
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert content[1]["type"] == "text"
    assert captured["model"] == "claude-sonnet-5-5"
    assert result["elements"][0]["confidence"] == 1.0
    assert result["is_food"] is True
    assert set(result.keys()) == {
        "is_food",
        "not_food_reason",
        "dish_name_guess",
        "cuisine_guess",
        "elements",
    }
    assert set(result["elements"][0].keys()) == {"name", "description", "confidence"}


def test_non_food_photo_flags_is_food_false_with_a_friendly_reason(monkeypatch):
    """A non-food image comes back is_food=False, and a blank reason from the model is
    backfilled with the friendly default (the state machine shows it to the user)."""
    monkeypatch.setattr(config, "anthropic_vision_model", lambda: "claude-sonnet-5-5")
    monkeypatch.setattr(anthropic_client, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "read_object", lambda key: (b"notfood", "image/jpeg"))
    monkeypatch.setattr(
        anthropic_client,
        "generate_structured",
        lambda **kwargs: {
            "is_food": False,
            "not_food_reason": "",
            "dish_name_guess": "",
            "cuisine_guess": "",
            "elements": [],
        },
    )

    result = vision_guess.run({"image_key": "uploads/a-cat.jpg"})

    assert result["is_food"] is False
    assert result["not_food_reason"] == vision_guess._NOT_FOOD_MESSAGE


def test_non_food_reason_from_model_is_kept(monkeypatch):
    monkeypatch.setattr(config, "anthropic_vision_model", lambda: "claude-sonnet-5-5")
    monkeypatch.setattr(anthropic_client, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "read_object", lambda key: (b"notfood", "image/jpeg"))
    monkeypatch.setattr(
        anthropic_client,
        "generate_structured",
        lambda **kwargs: {
            "is_food": False,
            "not_food_reason": "That is a very good dog, but not dinner.",
            "dish_name_guess": "",
            "cuisine_guess": "",
            "elements": [],
        },
    )

    result = vision_guess.run({"image_key": "uploads/a-dog.jpg"})

    assert result["is_food"] is False
    assert result["not_food_reason"] == "That is a very good dog, but not dinner."


def test_unsupported_content_type_falls_back_to_jpeg(monkeypatch):
    monkeypatch.setattr(config, "anthropic_vision_model", lambda: "claude-sonnet-5-5")
    monkeypatch.setattr(anthropic_client, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "read_object", lambda key: (b"bytes", "application/octet-stream"))
    monkeypatch.setattr(
        anthropic_client,
        "generate_structured",
        lambda **kwargs: {"dish_name_guess": "d", "cuisine_guess": "c", "elements": []},
    )

    block = vision_guess._image_block("uploads/x.jpg")
    assert block["source"]["media_type"] == "image/jpeg"
