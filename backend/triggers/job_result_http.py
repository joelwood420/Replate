import json

import azure.functions as func

from shared import blob, db
from shared.auth import get_user_oid
from shared.models import JobStatus

bp = func.Blueprint()

# Statuses for which a JobResults row exists. Stage 1 writes that row and leaves the
# job Identified, so the result is available well before any recipe is generated.
_STATUSES_WITH_RESULT = (JobStatus.IDENTIFIED, JobStatus.GENERATING, JobStatus.COMPLETED)


def _fetch_job(job_id: str, conn) -> dict | None:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT JobId, UserId, Status, ErrorMessage, ImageBlobUrl, IsSaved, CreatedAt FROM Jobs WHERE JobId = ?",
        job_id,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "job_id": str(row.JobId),
        "user_id": str(row.UserId),
        "status": row.Status,
        "error_message": row.ErrorMessage,
        "image_url": blob.generate_read_sas_url(row.ImageBlobUrl),
        "is_saved": bool(row.IsSaved),
        "created_at": db.to_utc_iso(row.CreatedAt),
    }


def _fetch_elements(job_id: str, conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ElementId, Name, Description, Role FROM DishElements WHERE JobId = ? ORDER BY SortOrder", job_id
    )
    elements = []
    for element_row in cursor.fetchall():
        element_id = element_row.ElementId

        cursor.execute(
            "SELECT IngredientName, Amount, Unit FROM ElementIngredients WHERE ElementId = ? ORDER BY SortOrder",
            element_id,
        )
        ingredients = [
            {"ingredient_name": r.IngredientName, "amount": r.Amount, "unit": r.Unit} for r in cursor.fetchall()
        ]

        cursor.execute(
            "SELECT StepNumber, Instruction FROM ElementSteps WHERE ElementId = ? ORDER BY StepNumber",
            element_id,
        )
        steps = [{"step_number": r.StepNumber, "instruction": r.Instruction} for r in cursor.fetchall()]

        elements.append(
            {
                "name": element_row.Name,
                "description": element_row.Description,
                "role": element_row.Role,
                "ingredients": ingredients,
                "steps": steps,
            }
        )
    return elements


def _fetch_result(job_id: str, conn) -> dict | None:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT jr.DishName, jr.Cuisine, jr.Confidence, jr.MatchedRestaurantId, jr.MatchedMenuItemId, "
        "jr.MatchConfidence, jr.MatchMethod, r.Name AS RestaurantName "
        "FROM JobResults jr LEFT JOIN Restaurants r ON r.RestaurantId = jr.MatchedRestaurantId "
        "WHERE jr.JobId = ?",
        job_id,
    )
    result_row = cursor.fetchone()
    if result_row is None:
        return None

    return {
        "dish_name": result_row.DishName,
        "cuisine": result_row.Cuisine,
        "confidence": result_row.Confidence,
        "matched_restaurant_id": result_row.MatchedRestaurantId,
        "restaurant_name": result_row.RestaurantName,
        "matched_menu_item_id": str(result_row.MatchedMenuItemId) if result_row.MatchedMenuItemId else None,
        "match_confidence": result_row.MatchConfidence,
        "match_method": result_row.MatchMethod,
        "elements": _fetch_elements(job_id, conn),
    }


def run(job_id: str, user_oid: str) -> dict:
    with db.get_connection() as conn:
        job = _fetch_job(job_id, conn)
        if job is None:
            return {"status_code": 404, "body": {"error": "Job not found"}}
        if job["user_id"] != user_oid:
            return {"status_code": 403, "body": {"error": "Not authorized to view this job"}}

        response_body = {
            "job_id": job["job_id"],
            "status": job["status"],
            "image_url": job["image_url"],
            "is_saved": job["is_saved"],
            "created_at": job["created_at"],
        }
        # An Identified job carries an error message when a previous reverse-engineer
        # attempt failed - it stays retryable, so surface the error without the job
        # being Failed.
        if job["error_message"]:
            response_body["error_message"] = job["error_message"]
        # `result` exists from stage 1 onward, not just when a recipe has been
        # generated, so the frontend can show the dish, restaurant and confidence
        # badge while `result.elements` is still empty.
        if job["status"] in _STATUSES_WITH_RESULT:
            response_body["result"] = _fetch_result(job_id, conn)

        return {"status_code": 200, "body": response_body}


@bp.route(route="jobs/{jobId}", methods=["GET"])
def job_result_http(req: func.HttpRequest) -> func.HttpResponse:
    outcome = run(req.route_params.get("jobId"), get_user_oid(req))
    return func.HttpResponse(
        json.dumps(outcome["body"]), status_code=outcome["status_code"], mimetype="application/json"
    )
