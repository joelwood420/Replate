"""Persistence activities for both stages of the pipeline.

The pipeline is split in two, so persistence is too:

- `persist_match_result` closes out stage 1 (identify + menu match). It writes the
  result item and moves the job to Identified, auto-saving it into the user's
  cookbook. No recipe exists at this point.
- `persist_recipe_result` closes out stage 2 (recipe generation, user-triggered).
  It writes the dish elements and moves the job to Completed.

`mark_job_failed` fails a job outright (stage 1); `mark_recipe_failed` returns it to
Identified so the user can retry generation without losing the menu match.
"""

import azure.durable_functions as df

from shared import repository
from shared.models import JobStatus

bp = df.Blueprint()

# Step Functions wraps a failed task's Cause in a long message including the full
# remote stack trace. DynamoDB items cap at 400 KB, so this is no longer a column
# width concern - but an error message the size of a stack trace is still noise in
# every API response that returns it, and an error-handling path that itself fails
# leaves the job stranded in a non-terminal status with no record of why.
_ERROR_MESSAGE_MAX_LEN = 1000


def _truncate_error(message) -> str | None:
    if message is None:
        return None
    text = str(message)
    if len(text) <= _ERROR_MESSAGE_MAX_LEN:
        return text
    return text[: _ERROR_MESSAGE_MAX_LEN - 1] + "…"


def run_match(activity_input: dict) -> None:
    job_id = activity_input["job_id"]
    match_result = activity_input["match_result"]
    vision_guess = activity_input.get("vision_guess")

    repository.put_job_result(job_id, match_result, vision_guess)

    # is_saved=True is the auto-save into the cookbook: photographing a dish already
    # implies wanting to keep it, so there is no separate "save this?" step.
    #
    # dish_name and restaurant_name are written onto the job as well because the
    # cookbook listing reads them from the user's partition - there is no join to
    # pull them back from the result item. `repository.update_job` mirrors them onto
    # the listing projection.
    repository.update_job(
        job_id,
        status=JobStatus.IDENTIFIED,
        is_saved=True,
        dish_name=match_result.get("dish_name"),
        restaurant_name=repository.get_restaurant_name(match_result.get("matched_restaurant_id")),
    )


def run_recipe(activity_input: dict) -> None:
    job_id = activity_input["job_id"]
    recreation = activity_input["recreation"]

    repository.replace_dish_elements(job_id, recreation.get("elements", []))

    # error_message is cleared so a successful retry doesn't leave the previous
    # attempt's error hanging around on a Completed job.
    repository.update_job(job_id, status=JobStatus.COMPLETED, error_message=None)


def run_mark_failed(activity_input: dict) -> None:
    repository.update_job(
        activity_input["job_id"],
        status=JobStatus.FAILED,
        error_message=_truncate_error(activity_input.get("error_message")),
    )


def run_mark_recipe_failed(activity_input: dict) -> None:
    """Send a job back to Identified after a failed recipe generation.

    Deliberately not Failed: stage 1 succeeded, so the restaurant match and dish
    identification are still good. Reverting lets the frontend show the error
    inline next to a working "Reverse engineer" button.
    """
    repository.update_job(
        activity_input["job_id"],
        status=JobStatus.IDENTIFIED,
        error_message=_truncate_error(activity_input.get("error_message")),
    )


@bp.activity_trigger(input_name="activityInput")
def persist_match_result(activityInput: dict) -> None:
    run_match(activityInput)


@bp.activity_trigger(input_name="activityInput")
def persist_recipe_result(activityInput: dict) -> None:
    run_recipe(activityInput)


@bp.activity_trigger(input_name="activityInput")
def mark_job_failed(activityInput: dict) -> None:
    run_mark_failed(activityInput)


@bp.activity_trigger(input_name="activityInput")
def mark_recipe_failed(activityInput: dict) -> None:
    run_mark_recipe_failed(activityInput)
