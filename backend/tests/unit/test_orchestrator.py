from unittest.mock import MagicMock

import pytest

from orchestrators.dish_orchestrator import dish_orchestrator
from shared.models import JobStatus


def _job_input(**overrides):
    base = {"job_id": "job-1", "image_blob_url": "https://example.com/photo.jpg", "latitude": 1.0, "longitude": 2.0}
    base.update(overrides)
    return base


def _call_names(context):
    return [c.args[0] for c in context.call_activity.call_args_list]


def test_vision_task_created_before_first_yield():
    context = MagicMock()
    context.get_input.return_value = _job_input()

    gen = dish_orchestrator(context)
    next(gen)

    assert _call_names(context)[:2] == ["vision_guess", "geocode_restaurant_candidates"]


def test_happy_path_full_call_sequence():
    """Stage 1 stops at the menu match - recipe generation is a separate orchestrator."""
    context = MagicMock()
    context.get_input.return_value = _job_input()

    gen = dish_orchestrator(context)

    next(gen)  # yields geocode task
    gen.send(
        [{"restaurant_id": "stub-1", "name": "Trattoria Roma", "address": "100 Sample Ave", "menu_source_url": "https://x"}]
    )  # yields task_all([vision, menu])

    vision_guess_stub = {"dish_name_guess": "Pizza", "cuisine_guess": "Italian", "elements": []}
    menu_result_stub = {"items": [{"menu_item_id": "i1"}]}
    gen.send([vision_guess_stub, menu_result_stub])  # yields match_menu_item task

    match_result_stub = {"dish_name": "Pizza", "cuisine": "Italian", "match_method": "menu_matched"}
    gen.send(match_result_stub)  # yields persist_match_result task

    with pytest.raises(StopIteration) as excinfo:
        gen.send(None)
    assert excinfo.value.value == {"job_id": "job-1", "status": JobStatus.IDENTIFIED}

    assert _call_names(context) == [
        "vision_guess",
        "geocode_restaurant_candidates",
        "fetch_restaurant_menu",
        "match_menu_item",
        "persist_match_result",
    ]
    assert context.task_all.call_count == 1

    menu_call = context.call_activity.call_args_list[2]
    assert menu_call.args[0] == "fetch_restaurant_menu"
    assert menu_call.args[1] == {
        "restaurant_id": "stub-1",
        "restaurant_name": "Trattoria Roma",
        "restaurant_address": "100 Sample Ave",
        "menu_source_url": "https://x",
    }

    # The vision guess has to reach persistence: stage 2 reads it back out of the
    # database, and nothing else in the schema records it until a recipe exists.
    persist_call = context.call_activity.call_args_list[-1]
    assert persist_call.args[1] == {
        "job_id": "job-1",
        "match_result": match_result_stub,
        "vision_guess": vision_guess_stub,
    }


def test_never_generates_a_recipe():
    """The expensive generator must not run on upload - it is user-triggered now."""
    context = MagicMock()
    context.get_input.return_value = _job_input()

    gen = dish_orchestrator(context)
    next(gen)
    gen.send([{"restaurant_id": "stub-1", "name": "R", "address": "A", "menu_source_url": None}])
    gen.send([{"dish_name_guess": "Pizza", "elements": []}, {"items": []}])
    gen.send({"dish_name": "Pizza", "match_method": "menu_matched"})

    with pytest.raises(StopIteration):
        gen.send(None)

    call_names = _call_names(context)
    assert "generate_recreation" not in call_names
    assert "query_culinary_embeddings" not in call_names


def test_skips_fetch_menu_when_no_candidates_found():
    context = MagicMock()
    context.get_input.return_value = _job_input(latitude=0.0, longitude=0.0)

    gen = dish_orchestrator(context)
    next(gen)  # yields geocode task
    gen.send([])  # candidates empty -> yields vision_task directly, no new call

    vision_guess_stub = {"dish_name_guess": "Pizza", "cuisine_guess": "Italian", "elements": []}
    gen.send(vision_guess_stub)  # yields match_menu_item task

    call_names = _call_names(context)
    assert "fetch_restaurant_menu" not in call_names
    assert call_names[-1] == "match_menu_item"

    match_call = context.call_activity.call_args_list[-1]
    assert match_call.args[0] == "match_menu_item"
    assert match_call.args[1]["candidate_found"] is False
    assert match_call.args[1]["restaurant_id"] is None
    assert context.task_all.call_count == 0


def test_selected_restaurant_routes_to_select_restaurant_candidate_activity():
    context = MagicMock()
    context.get_input.return_value = _job_input(selected_restaurant_id="place-1")

    gen = dish_orchestrator(context)
    next(gen)

    assert _call_names(context)[:2] == ["vision_guess", "select_restaurant_candidate"]
    select_call = context.call_activity.call_args_list[1]
    assert select_call.args[1] == {"job_id": "job-1", "restaurant_id": "place-1"}


def test_selected_restaurant_never_calls_geocode():
    context = MagicMock()
    context.get_input.return_value = _job_input(selected_restaurant_id="place-1")

    gen = dish_orchestrator(context)
    next(gen)
    gen.send([{"restaurant_id": "place-1", "name": "Luigi's", "address": "123 Main St", "menu_source_url": None}])

    assert "geocode_restaurant_candidates" not in _call_names(context)


def test_exception_triggers_mark_job_failed_and_reraises():
    context = MagicMock()
    context.get_input.return_value = _job_input()

    gen = dish_orchestrator(context)
    next(gen)  # yields geocode task
    gen.throw(RuntimeError("boom"))  # simulates geocode activity failure; yields mark_job_failed task

    with pytest.raises(RuntimeError, match="boom"):
        gen.send(None)

    assert _call_names(context)[-1] == "mark_job_failed"
    mark_failed_call = context.call_activity.call_args_list[-1]
    assert mark_failed_call.args[1] == {"job_id": "job-1", "error_message": "boom"}
