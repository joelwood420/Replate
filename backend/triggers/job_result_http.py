import json

import azure.functions as func

from shared import repository, storage
from shared.auth import get_user_oid
from shared.models import JobStatus

bp = func.Blueprint()

# Statuses for which a result item exists. Stage 1 writes that item and leaves the
# job Identified, so the result is available well before any recipe is generated.
_STATUSES_WITH_RESULT = (JobStatus.IDENTIFIED, JobStatus.GENERATING, JobStatus.COMPLETED)


def _fetch_result(job_id: str) -> dict | None:
    """Assemble the result payload.

    The restaurant name was a LEFT JOIN; it is now an explicit point lookup, which
    is one extra round trip only when a menu match was actually found. Elements
    come back from a single query because their ingredients and steps are nested
    inside each element item.
    """
    result = repository.get_job_result(job_id)
    if result is None:
        return None

    return {
        "dish_name": result.get("dish_name"),
        "cuisine": result.get("cuisine"),
        "confidence": result.get("confidence"),
        "matched_restaurant_id": result.get("matched_restaurant_id"),
        "restaurant_name": repository.get_restaurant_name(result.get("matched_restaurant_id")),
        "matched_menu_item_id": result.get("matched_menu_item_id"),
        "match_confidence": result.get("match_confidence"),
        "match_method": result.get("match_method"),
        "elements": repository.get_dish_elements(job_id),
    }


def run(job_id: str, user_oid: str) -> dict:
    job = repository.get_job(job_id)
    if job is None:
        return {"status_code": 404, "body": {"error": "Job not found"}}
    if job["user_id"] != user_oid:
        return {"status_code": 403, "body": {"error": "Not authorized to view this job"}}

    response_body = {
        "job_id": job["job_id"],
        "status": job["status"],
        "image_url": storage.generate_read_url(job["image_key"]),
        "is_saved": bool(job.get("is_saved")),
        "created_at": job["created_at"],
    }
    # An Identified job carries an error message when a previous reverse-engineer
    # attempt failed - it stays retryable, so surface the error without the job
    # being Failed.
    if job.get("error_message"):
        response_body["error_message"] = job["error_message"]
    # `result` exists from stage 1 onward, not just when a recipe has been
    # generated, so the frontend can show the dish, restaurant and confidence
    # badge while `result.elements` is still empty.
    if job["status"] in _STATUSES_WITH_RESULT:
        response_body["result"] = _fetch_result(job_id)

    return {"status_code": 200, "body": response_body}


@bp.route(route="jobs/{jobId}", methods=["GET"])
def job_result_http(req: func.HttpRequest) -> func.HttpResponse:
    outcome = run(req.route_params.get("jobId"), get_user_oid(req))
    return func.HttpResponse(
        json.dumps(outcome["body"]), status_code=outcome["status_code"], mimetype="application/json"
    )
