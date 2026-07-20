import uuid

import azure.durable_functions as df

from shared import db
from shared.models import JobStatus

bp = df.Blueprint()


def _execute(activity_input: dict, conn) -> None:
    job_id = activity_input["job_id"]
    match_result = activity_input["match_result"]
    recreation = activity_input["recreation"]

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO JobResults (JobId, DishName, Cuisine, Confidence, MatchedRestaurantId, "
        "MatchedMenuItemId, MatchConfidence, MatchMethod) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        job_id,
        match_result.get("dish_name"),
        match_result.get("cuisine"),
        match_result.get("vision_confidence"),
        match_result.get("matched_restaurant_id"),
        match_result.get("matched_menu_item_id"),
        match_result.get("match_confidence"),
        match_result.get("match_method"),
    )

    for element in recreation.get("elements", []):
        element_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO DishElements (ElementId, JobId, Name, Description, SortOrder) VALUES (?, ?, ?, ?, ?)",
            element_id,
            job_id,
            element["name"],
            element.get("description"),
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

    cursor.execute(
        "UPDATE Jobs SET Status = ?, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.COMPLETED,
        job_id,
    )


def run(activity_input: dict) -> None:
    with db.get_connection() as conn:
        _execute(activity_input, conn)


def _execute_mark_failed(activity_input: dict, conn) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Jobs SET Status = ?, ErrorMessage = ?, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.FAILED,
        activity_input.get("error_message"),
        activity_input["job_id"],
    )


def run_mark_failed(activity_input: dict) -> None:
    with db.get_connection() as conn:
        _execute_mark_failed(activity_input, conn)


@bp.activity_trigger(input_name="activityInput")
def persist_job_result(activityInput: dict) -> None:
    run(activityInput)


@bp.activity_trigger(input_name="activityInput")
def mark_job_failed(activityInput: dict) -> None:
    run_mark_failed(activityInput)
