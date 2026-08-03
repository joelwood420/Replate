import json
from unittest.mock import MagicMock

from activities import persist_job_result
from shared.models import JobStatus, MatchMethod

_MATCH_RESULT = {
    "dish_name": "Margherita Pizza",
    "cuisine": "Italian",
    "vision_confidence": 0.8,
    "matched_restaurant_id": "stub-1",
    "matched_menu_item_id": "item-1",
    "match_confidence": 0.9,
    "match_method": MatchMethod.MENU_MATCHED,
}

_VISION_GUESS = {
    "dish_name_guess": "Pizza",
    "cuisine_guess": "Italian",
    "elements": [{"name": "Crust", "description": "Charred", "confidence": 0.8}],
}

_RECREATION = {
    "elements": [
        {
            "name": "Crust",
            "description": "desc",
            "role": "Component",
            "sort_order": 1,
            "ingredients": [{"ingredient_name": "Flour", "amount": "2", "unit": "cup", "sort_order": 1}],
            "steps": [{"step_number": 1, "instruction": "Mix and knead."}],
        }
    ]
}


def _executed_sql(conn):
    return [c.args[0] for c in conn.cursor().execute.call_args_list]


def _calls_matching(conn, fragment):
    return [c for c in conn.cursor().execute.call_args_list if fragment in c.args[0]]


# --- stage 1: persist_match_result -----------------------------------------


def test_match_writes_job_results_row_without_any_recipe():
    conn = MagicMock()

    persist_job_result._execute_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}, conn
    )

    executed = _executed_sql(conn)
    assert any("INSERT INTO JobResults" in s for s in executed)
    # Stage 1 must not write any part of the recipe tree - that's stage 2's job.
    assert not any("INSERT INTO DishElements" in s for s in executed)
    assert not any("INSERT INTO ElementIngredients" in s for s in executed)
    assert not any("INSERT INTO ElementSteps" in s for s in executed)


def test_match_persists_vision_guess_as_json():
    """Stage 2 reads this back - it is the only record of the vision guess."""
    conn = MagicMock()

    persist_job_result._execute_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}, conn
    )

    insert = _calls_matching(conn, "INSERT INTO JobResults")[0]
    assert "VisionGuessJson" in insert.args[0]
    assert json.loads(insert.args[-1]) == _VISION_GUESS


def test_match_sets_status_identified_and_auto_saves_to_cookbook():
    conn = MagicMock()

    persist_job_result._execute_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}, conn
    )

    updates = _calls_matching(conn, "UPDATE Jobs")
    assert len(updates) == 1
    assert "IsSaved = 1" in updates[0].args[0]
    assert updates[0].args[1] == JobStatus.IDENTIFIED
    assert updates[0].args[2] == "job-123"


def test_match_tolerates_missing_vision_guess():
    conn = MagicMock()

    persist_job_result._execute_match({"job_id": "job-123", "match_result": _MATCH_RESULT}, conn)

    insert = _calls_matching(conn, "INSERT INTO JobResults")[0]
    assert insert.args[-1] is None


# --- stage 2: persist_recipe_result ----------------------------------------


def test_recipe_writes_element_ingredient_and_step_rows():
    conn = MagicMock()

    persist_job_result._execute_recipe({"job_id": "job-123", "recreation": _RECREATION}, conn)

    executed = _executed_sql(conn)
    assert any("INSERT INTO DishElements" in s for s in executed)
    assert any("INSERT INTO ElementIngredients" in s for s in executed)
    assert any("INSERT INTO ElementSteps" in s for s in executed)
    # Stage 1 already wrote the JobResults row; stage 2 must not insert a second one
    # (JobId is the primary key, so it would throw).
    assert not any("INSERT INTO JobResults" in s for s in executed)


def test_recipe_sets_status_completed_and_clears_error():
    conn = MagicMock()

    persist_job_result._execute_recipe({"job_id": "job-123", "recreation": {"elements": []}}, conn)

    updates = _calls_matching(conn, "UPDATE Jobs")
    assert len(updates) == 1
    assert "ErrorMessage = NULL" in updates[0].args[0]
    assert updates[0].args[1] == JobStatus.COMPLETED
    assert updates[0].args[2] == "job-123"


def test_recipe_clears_previous_elements_before_inserting():
    """Re-running generation must replace the recipe, not duplicate it.

    There is no unique key on DishElements (JobId, SortOrder), so without the
    delete a retry would silently double every element, ingredient and step.
    """
    conn = MagicMock()

    persist_job_result._execute_recipe({"job_id": "job-123", "recreation": _RECREATION}, conn)

    executed = _executed_sql(conn)
    # Children first - the foreign keys are NO ACTION, so nothing cascades.
    assert executed[0].startswith("DELETE FROM ElementSteps")
    assert executed[1].startswith("DELETE FROM ElementIngredients")
    assert executed[2].startswith("DELETE FROM DishElements")
    assert executed.index("DELETE FROM DishElements WHERE JobId = ?") < next(
        i for i, s in enumerate(executed) if "INSERT INTO DishElements" in s
    )


def test_recipe_run_twice_produces_the_same_row_count():
    first, second = MagicMock(), MagicMock()

    persist_job_result._execute_recipe({"job_id": "job-123", "recreation": _RECREATION}, first)
    persist_job_result._execute_recipe({"job_id": "job-123", "recreation": _RECREATION}, second)

    def insert_count(conn):
        return len([s for s in _executed_sql(conn) if s.startswith("INSERT INTO")])

    assert insert_count(first) == insert_count(second)


# --- failure activities ----------------------------------------------------


def test_mark_job_failed_sets_status_and_error_message():
    conn = MagicMock()

    persist_job_result._execute_mark_failed({"job_id": "job-123", "error_message": "boom"}, conn)

    call = conn.cursor().execute.call_args
    assert "UPDATE Jobs" in call.args[0]
    assert call.args[1] == JobStatus.FAILED
    assert call.args[2] == "boom"
    assert call.args[3] == "job-123"


def test_error_messages_are_truncated_to_fit_the_column():
    """Jobs.ErrorMessage is NVARCHAR(1000).

    Durable wraps activity failures in a message containing the whole remote stack trace,
    which overflows the column. An error handler that throws leaves the job stuck in a
    non-terminal status forever with no record of why, so truncation matters.
    """
    long_error = "x" * 5000

    for execute in (
        persist_job_result._execute_mark_failed,
        persist_job_result._execute_mark_recipe_failed,
    ):
        conn = MagicMock()
        execute({"job_id": "job-123", "error_message": long_error}, conn)

        written = conn.cursor().execute.call_args.args[2]
        assert len(written) == 1000
        assert written.endswith("…")


def test_mark_recipe_failed_reverts_to_identified_not_failed():
    """A transient generator error must leave the dish usable and retryable."""
    conn = MagicMock()

    persist_job_result._execute_mark_recipe_failed(
        {"job_id": "job-123", "error_message": "generator exploded"}, conn
    )

    call = conn.cursor().execute.call_args
    assert "UPDATE Jobs" in call.args[0]
    assert call.args[1] == JobStatus.IDENTIFIED
    assert call.args[2] == "generator exploded"
    assert call.args[3] == "job-123"
