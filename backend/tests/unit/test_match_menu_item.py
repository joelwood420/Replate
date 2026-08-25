import pytest

from activities import match_menu_item
from shared import anthropic_client
from shared.models import MatchMethod


def _use_llm(monkeypatch, outcome):
    """Configure the classifier and stub the model call. `outcome` is the structured dict the
    model would return, or an AnthropicError to raise."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MATCH_MODEL", "claude-test")

    calls = []

    def fake_structured(model, messages, schema, system=None, **kwargs):
        calls.append({"model": model, "messages": messages})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(match_menu_item.anthropic_client, "generate_structured", fake_structured)
    return calls


# --- difflib fallback path (no model configured in the test env) ------------


def test_high_confidence_menu_item_matched(sample_vision_guess, sample_menu_items):
    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["match_method"] == MatchMethod.MENU_MATCHED
    assert result["matched_menu_item_id"] == "item-1"
    assert result["matched_restaurant_id"] == "stub-1"
    assert result["match_confidence"] >= 0.6


def test_medium_confidence_vision_only_when_menu_found_but_no_item_matches(sample_vision_guess):
    unrelated_menu = [
        {
            "menu_item_id": "item-9",
            "item_name": "Xyzzy Noodle Bowl",
            "item_description": "Completely unrelated dish description",
            "price": "99.00",
        }
    ]

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": unrelated_menu,
            "candidate_found": True,
            "restaurant_id": "stub-2",
        }
    )

    assert result["match_method"] == MatchMethod.VISION_ONLY_MEDIUM
    assert result["matched_menu_item_id"] is None
    assert result["matched_restaurant_id"] == "stub-2"


def test_low_confidence_vision_only_when_no_restaurant_found(sample_vision_guess):
    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": [],
            "candidate_found": False,
            "restaurant_id": None,
        }
    )

    assert result["match_method"] == MatchMethod.VISION_ONLY_LOW
    assert result["matched_menu_item_id"] is None
    assert result["matched_restaurant_id"] is None
    assert result["match_confidence"] == 0.0


def test_picks_best_scoring_item_among_multiple_candidates(sample_vision_guess, sample_menu_items):
    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["matched_menu_item_id"] == "item-1"


def test_confidence_threshold_boundary_behavior(monkeypatch, sample_vision_guess, sample_menu_items):
    monkeypatch.setenv("MENU_MATCH_CONFIDENCE_THRESHOLD", "1.1")

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["match_method"] == MatchMethod.VISION_ONLY_MEDIUM
    assert result["matched_menu_item_id"] is None


# --- LLM classifier path ----------------------------------------------------


def test_llm_match_selects_the_chosen_item(monkeypatch, sample_vision_guess, sample_menu_items):
    calls = _use_llm(monkeypatch, {"match_index": 1, "confidence": 0.91})

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert len(calls) == 1
    assert result["match_method"] == MatchMethod.MENU_MATCHED
    # index 1 is Spaghetti Carbonara - the model's pick is trusted over a character match.
    assert result["matched_menu_item_id"] == "item-2"
    assert result["dish_name"] == "Spaghetti Carbonara"
    # The full menu description is carried alongside the short name so recipe
    # generation can ground on components the title omits.
    assert result["dish_description"] == "Pasta with egg, pecorino, guanciale, and black pepper"
    assert result["match_confidence"] == 0.91


def test_vision_only_outcomes_have_no_menu_description(sample_vision_guess):
    """Only a menu match has a real description; the vision-only paths carry None."""
    low = match_menu_item.run(
        {"vision_guess": sample_vision_guess, "menu_items": [], "candidate_found": False, "restaurant_id": None}
    )
    medium = match_menu_item.run(
        {"vision_guess": sample_vision_guess, "menu_items": [], "candidate_found": True, "restaurant_id": "stub-3"}
    )

    assert low["dish_description"] is None
    assert medium["dish_description"] is None


def test_llm_none_yields_vision_only_medium(monkeypatch, sample_vision_guess, sample_menu_items):
    _use_llm(monkeypatch, {"match_index": -1, "confidence": 0.0})

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["match_method"] == MatchMethod.VISION_ONLY_MEDIUM
    assert result["matched_menu_item_id"] is None


def test_llm_low_confidence_yields_vision_only_medium(monkeypatch, sample_vision_guess, sample_menu_items):
    _use_llm(monkeypatch, {"match_index": 0, "confidence": 0.3})

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["match_method"] == MatchMethod.VISION_ONLY_MEDIUM


def test_llm_out_of_range_index_is_treated_as_none(monkeypatch, sample_vision_guess, sample_menu_items):
    """The model must only point at a listed item; a slip off the end can never match."""
    _use_llm(monkeypatch, {"match_index": 99, "confidence": 0.99})

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["match_method"] == MatchMethod.VISION_ONLY_MEDIUM
    assert result["matched_menu_item_id"] is None


def test_falls_back_to_difflib_when_the_llm_call_errors(monkeypatch, sample_vision_guess, sample_menu_items):
    """An LLM failure must not lose matching entirely - difflib still finds the exact name."""
    _use_llm(monkeypatch, anthropic_client.AnthropicError("boom"))

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": sample_menu_items,
            "candidate_found": True,
            "restaurant_id": "stub-1",
        }
    )

    assert result["match_method"] == MatchMethod.MENU_MATCHED
    assert result["matched_menu_item_id"] == "item-1"


def test_no_llm_call_when_there_is_no_menu(monkeypatch, sample_vision_guess):
    calls = _use_llm(monkeypatch, {"match_index": 0, "confidence": 0.9})

    result = match_menu_item.run(
        {
            "vision_guess": sample_vision_guess,
            "menu_items": [],
            "candidate_found": True,
            "restaurant_id": "stub-3",
        }
    )

    assert calls == []
    assert result["match_method"] == MatchMethod.VISION_ONLY_MEDIUM
