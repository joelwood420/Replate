from unittest.mock import MagicMock

import pytest

from orchestrators.recipe_orchestrator import recipe_orchestrator
from shared.models import JobStatus, MatchMethod


def _recipe_input(**overrides):
    base = {
        "job_id": "job-1",
        "vision_guess": {
            "dish_name_guess": "Pad Thai",
            "cuisine_guess": "Thai",
            "elements": [{"name": "Noodles", "description": "Rice noodles", "confidence": 0.8}],
        },
        "match_result": {
            "dish_name": "Pad Thai Goong",
            "cuisine": "Thai",
            "match_method": MatchMethod.MENU_MATCHED,
        },
    }
    base.update(overrides)
    return base


def _call_names(context):
    return [c.args[0] for c in context.call_activity.call_args_list]


def test_happy_path_call_sequence():
    context = MagicMock()
    context.get_input.return_value = _recipe_input()

    gen = recipe_orchestrator(context)

    next(gen)  # yields query_culinary_embeddings task
    gen.send([{"source_text": "Blooming spices", "distance": 0.1}])  # yields generate_recreation
    recreation_stub = {"elements": [{"name": "Noodles", "sort_order": 0}]}
    gen.send(recreation_stub)  # yields persist_recipe_result

    with pytest.raises(StopIteration) as excinfo:
        gen.send(None)
    assert excinfo.value.value == {"job_id": "job-1", "status": JobStatus.COMPLETED}

    assert _call_names(context) == [
        "query_culinary_embeddings",
        "generate_recreation",
        "persist_recipe_result",
    ]

    persist_call = context.call_activity.call_args_list[-1]
    assert persist_call.args[1] == {"job_id": "job-1", "recreation": recreation_stub}


def test_embedding_query_prefers_matched_menu_item_name():
    context = MagicMock()
    context.get_input.return_value = _recipe_input()

    gen = recipe_orchestrator(context)
    next(gen)

    query_call = context.call_activity.call_args_list[0]
    assert query_call.args[0] == "query_culinary_embeddings"
    # The real menu item's name beats the vision model's unaided guess.
    assert query_call.args[1]["query_text"] == "Pad Thai Goong"
    # top_k is left to the activity so no env var is read inside a replayed orchestrator.
    assert "top_k" not in query_call.args[1]


def test_falls_back_to_vision_guess_name_when_no_menu_match():
    context = MagicMock()
    context.get_input.return_value = _recipe_input(
        match_result={"dish_name": None, "cuisine": None, "match_method": MatchMethod.VISION_ONLY_LOW}
    )

    gen = recipe_orchestrator(context)
    next(gen)

    assert context.call_activity.call_args_list[0].args[1]["query_text"] == "Pad Thai"


def test_exception_reverts_to_identified_and_reraises():
    """A failed generation must not discard a good menu match."""
    context = MagicMock()
    context.get_input.return_value = _recipe_input()

    gen = recipe_orchestrator(context)
    next(gen)
    gen.throw(RuntimeError("generator exploded"))  # yields mark_recipe_failed task

    with pytest.raises(RuntimeError, match="generator exploded"):
        gen.send(None)

    assert _call_names(context)[-1] == "mark_recipe_failed"
    assert context.call_activity.call_args_list[-1].args[1] == {
        "job_id": "job-1",
        "error_message": "generator exploded",
    }
    # Explicitly not the stage-1 failure path, which would mark the job Failed.
    assert "mark_job_failed" not in _call_names(context)
