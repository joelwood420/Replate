"""Persistence activities for both stages of the pipeline.

The pipeline is split in two, so persistence is too:

- `persist_match_result` closes out stage 1 (identify + menu match). It writes the
  JobResults row and moves the job to Identified, auto-saving it into the user's
  cookbook. No recipe exists at this point.
- `persist_recipe_result` closes out stage 2 (recipe generation, user-triggered).
  It writes the DishElements/ElementIngredients/ElementSteps tree and moves the job
  to Completed.

`mark_job_failed` fails a job outright (stage 1); `mark_recipe_failed` returns it to
Identified so the user can retry generation without losing the menu match.
"""

import json
import uuid

import azure.durable_functions as df

from shared import db
from shared.models import JobStatus

bp = df.Blueprint()

# Jobs.ErrorMessage is NVARCHAR(1000). Durable wraps activity failures in a long message
# that includes the full remote stack trace, which overflows it - and an error-handling
# activity that throws leaves the job stranded in its non-terminal status forever, with no
# record of why. Truncating is strictly better than losing the status transition.
_ERROR_MESSAGE_MAX_LEN = 1000


def _truncate_error(message) -> str | None:
    if message is None:
        return None
    text = str(message)
    if len(text) <= _ERROR_MESSAGE_MAX_LEN:
        return text
    return text[: _ERROR_MESSAGE_MAX_LEN - 1] + "…"


def _execute_match(activity_input: dict, conn) -> None:
    job_id = activity_input["job_id"]
    match_result = activity_input["match_result"]
    vision_guess = activity_input.get("vision_guess")

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO JobResults (JobId, DishName, Cuisine, Confidence, MatchedRestaurantId, "
        "MatchedMenuItemId, MatchConfidence, MatchMethod, VisionGuessJson) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        job_id,
        match_result.get("dish_name"),
        match_result.get("cuisine"),
        match_result.get("vision_confidence"),
        match_result.get("matched_restaurant_id"),
        match_result.get("matched_menu_item_id"),
        match_result.get("match_confidence"),
        match_result.get("match_method"),
        json.dumps(vision_guess) if vision_guess is not None else None,
    )

    # IsSaved = 1 is the auto-save into the cookbook: photographing a dish already
    # implies wanting to keep it, so there is no separate "save this?" step.
    cursor.execute(
        "UPDATE Jobs SET Status = ?, IsSaved = 1, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.IDENTIFIED,
        job_id,
    )


def run_match(activity_input: dict) -> None:
    with db.get_connection() as conn:
        _execute_match(activity_input, conn)


def _delete_existing_elements(cursor, job_id: str) -> None:
    """Clear any previously generated recipe for this job.

    Makes `persist_recipe_result` safe to re-run: there is no unique key on
    (JobId, SortOrder), so without this a second generation would silently
    duplicate every element. Children go first - the foreign keys are NO ACTION,
    so nothing cascades.
    """
    child_scope = "WHERE ElementId IN (SELECT ElementId FROM DishElements WHERE JobId = ?)"
    cursor.execute(f"DELETE FROM ElementSteps {child_scope}", job_id)
    cursor.execute(f"DELETE FROM ElementIngredients {child_scope}", job_id)
    cursor.execute("DELETE FROM DishElements WHERE JobId = ?", job_id)


def _execute_recipe(activity_input: dict, conn) -> None:
    job_id = activity_input["job_id"]
    recreation = activity_input["recreation"]

    cursor = conn.cursor()
    _delete_existing_elements(cursor, job_id)

    for element in recreation.get("elements", []):
        element_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO DishElements (ElementId, JobId, Name, Description, Role, SortOrder) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            element_id,
            job_id,
            element["name"],
            element.get("description"),
            element.get("role"),
            element["sort_order"],
        )
        for ingredient in element.get("ingredients", []):
            cursor.execute(
                "INSERT INTO ElementIngredients (ElementId, IngredientName, Amount, Unit, SortOrder) "
                "VALUES (?, ?, ?, ?, ?)",
                element_id,
                ingredient["ingredient_name"],
                ingredient.get("amount"),
                ingredient.get("unit"),
                ingredient["sort_order"],
            )
        for step in element.get("steps", []):
            cursor.execute(
                "INSERT INTO ElementSteps (ElementId, StepNumber, Instruction) VALUES (?, ?, ?)",
                element_id,
                step["step_number"],
                step["instruction"],
            )

    # ErrorMessage is cleared so a successful retry doesn't leave the previous
    # attempt's error hanging around on a Completed job.
    cursor.execute(
        "UPDATE Jobs SET Status = ?, ErrorMessage = NULL, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.COMPLETED,
        job_id,
    )


def run_recipe(activity_input: dict) -> None:
    with db.get_connection() as conn:
        _execute_recipe(activity_input, conn)


def _execute_mark_failed(activity_input: dict, conn) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Jobs SET Status = ?, ErrorMessage = ?, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.FAILED,
        _truncate_error(activity_input.get("error_message")),
        activity_input["job_id"],
    )


def run_mark_failed(activity_input: dict) -> None:
    with db.get_connection() as conn:
        _execute_mark_failed(activity_input, conn)


def _execute_mark_recipe_failed(activity_input: dict, conn) -> None:
    """Send a job back to Identified after a failed recipe generation.

    Deliberately not Failed: stage 1 succeeded, so the restaurant match and dish
    identification are still good. Reverting lets the frontend show the error
    inline next to a working "Reverse engineer" button.
    """
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Jobs SET Status = ?, ErrorMessage = ?, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.IDENTIFIED,
        _truncate_error(activity_input.get("error_message")),
        activity_input["job_id"],
    )


def run_mark_recipe_failed(activity_input: dict) -> None:
    with db.get_connection() as conn:
        _execute_mark_recipe_failed(activity_input, conn)


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
