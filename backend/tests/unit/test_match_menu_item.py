from activities import match_menu_item
from shared.models import MatchMethod


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
