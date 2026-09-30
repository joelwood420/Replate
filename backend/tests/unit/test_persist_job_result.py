from activities import persist_job_result
from shared import repository
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


def _job(job_id="job-123", status=JobStatus.PROCESSING):
    return repository.create_job(
        job_id=job_id, user_oid="user-1", status=status, image_key="uploads/p.jpg"
    )


# --- stage 1: persist_match_result -----------------------------------------


def test_match_writes_the_result_without_any_recipe(ddb_table):
    _job()

    persist_job_result.run_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}
    )

    assert repository.get_job_result("job-123")["dish_name"] == "Margherita Pizza"
    # Stage 1 must not write any part of the recipe - that's stage 2's job.
    assert repository.get_dish_elements("job-123") == []


def test_match_persists_the_vision_guess(ddb_table):
    """Stage 2 reads this back - it is the only record of the vision guess.

    It is now a nested map rather than a JSON string, so there is nothing to
    serialise on the way in or parse on the way out.
    """
    _job()

    persist_job_result.run_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}
    )

    assert repository.get_job_result("job-123")["vision_guess"] == _VISION_GUESS


def test_match_sets_status_identified_and_auto_saves_to_cookbook(ddb_table):
    _job()

    persist_job_result.run_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}
    )

    job = repository.get_job("job-123")
    assert job["status"] == JobStatus.IDENTIFIED
    assert job["is_saved"] is True


def test_match_denormalises_dish_and_restaurant_onto_the_listing(ddb_table):
    """The cookbook list has no join to fall back on - if this is not written
    at match time, every row shows a blank dish name."""
    _job()
    repository.upsert_restaurant("stub-1", "Trattoria Roma", None, None, None, None)

    persist_job_result.run_match(
        {"job_id": "job-123", "match_result": _MATCH_RESULT, "vision_guess": _VISION_GUESS}
    )

    listed = repository.list_jobs("user-1")[0]
    assert listed["dish_name"] == "Margherita Pizza"
    assert listed["restaurant_name"] == "Trattoria Roma"


def test_match_tolerates_a_missing_restaurant(ddb_table):
    """Vision-only outcomes have no matched restaurant to look up."""
    _job()
    vision_only = {**_MATCH_RESULT, "matched_restaurant_id": None}

    persist_job_result.run_match(
        {"job_id": "job-123", "match_result": vision_only, "vision_guess": _VISION_GUESS}
    )

    assert repository.list_jobs("user-1")[0]["restaurant_name"] is None


def test_match_tolerates_missing_vision_guess(ddb_table):
    _job()

    persist_job_result.run_match({"job_id": "job-123", "match_result": _MATCH_RESULT})

    assert repository.get_job_result("job-123")["vision_guess"] is None


# --- stage 2: persist_recipe_result ----------------------------------------


def test_recipe_writes_elements_with_nested_ingredients_and_steps(ddb_table):
    _job(status=JobStatus.GENERATING)

    persist_job_result.run_recipe({"job_id": "job-123", "recreation": _RECREATION})

    elements = repository.get_dish_elements("job-123")
    assert len(elements) == 1
    assert elements[0]["ingredients"][0]["ingredient_name"] == "Flour"
    assert elements[0]["steps"][0]["instruction"] == "Mix and knead."


def test_recipe_does_not_disturb_the_stage_one_result(ddb_table):
    _job(status=JobStatus.GENERATING)
    persist_job_result.run_match({"job_id": "job-123", "match_result": _MATCH_RESULT})

    persist_job_result.run_recipe({"job_id": "job-123", "recreation": _RECREATION})

    assert repository.get_job_result("job-123")["dish_name"] == "Margherita Pizza"


def test_recipe_sets_status_completed_and_clears_error(ddb_table):
    _job(status=JobStatus.GENERATING)
    repository.update_job("job-123", error_message="a previous attempt failed")

    persist_job_result.run_recipe({"job_id": "job-123", "recreation": {"elements": []}})

    job = repository.get_job("job-123")
    assert job["status"] == JobStatus.COMPLETED
    assert job["error_message"] is None


def test_recipe_run_twice_does_not_duplicate_elements(ddb_table):
    """Re-running generation must replace the recipe, not append to it."""
    _job(status=JobStatus.GENERATING)

    persist_job_result.run_recipe({"job_id": "job-123", "recreation": _RECREATION})
    persist_job_result.run_recipe({"job_id": "job-123", "recreation": _RECREATION})

    assert len(repository.get_dish_elements("job-123")) == 1


# --- failure activities ----------------------------------------------------


def test_mark_job_failed_sets_status_and_error_message(ddb_table):
    _job()

    persist_job_result.run_mark_failed({"job_id": "job-123", "error_message": "boom"})

    job = repository.get_job("job-123")
    assert job["status"] == JobStatus.FAILED
    assert job["error_message"] == "boom"


def test_mark_job_failed_records_a_failure_code_when_given(ddb_table):
    """The vision step's not-food outcome passes a code so the app can show its own copy."""
    _job()

    persist_job_result.run_mark_failed(
        {"job_id": "job-123", "error_message": "That is a cat.", "failure_code": "not_food"}
    )

    assert repository.get_job("job-123")["failure_code"] == "not_food"


def test_mark_job_failed_without_a_code_leaves_none(ddb_table):
    _job()

    persist_job_result.run_mark_failed({"job_id": "job-123", "error_message": "boom"})

    assert "failure_code" not in repository.get_job("job-123")


def test_error_messages_are_truncated(ddb_table):
    """Step Functions wraps a failed task's Cause with the full remote stack trace.

    An error message the size of a stack trace is noise in every API response that
    returns it, and an error handler that itself fails leaves the job stranded in a
    non-terminal status with no record of why.
    """
    long_error = "x" * 5000

    for job_id, run in (
        ("job-a", persist_job_result.run_mark_failed),
        ("job-b", persist_job_result.run_mark_recipe_failed),
    ):
        _job(job_id=job_id)
        run({"job_id": job_id, "error_message": long_error})

        written = repository.get_job(job_id)["error_message"]
        assert len(written) == 1000
        assert written.endswith("…")


def test_mark_recipe_failed_reverts_to_identified_not_failed(ddb_table):
    """A transient generator error must leave the dish usable and retryable."""
    _job(status=JobStatus.GENERATING)

    persist_job_result.run_mark_recipe_failed(
        {"job_id": "job-123", "error_message": "generator exploded"}
    )

    job = repository.get_job("job-123")
    assert job["status"] == JobStatus.IDENTIFIED
    assert job["error_message"] == "generator exploded"


def test_a_failed_status_reaches_the_listing(ddb_table):
    _job()

    persist_job_result.run_mark_failed({"job_id": "job-123", "error_message": "boom"})

    assert repository.list_jobs("user-1")[0]["status"] == JobStatus.FAILED
