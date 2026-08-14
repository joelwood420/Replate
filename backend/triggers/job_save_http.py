import json

import azure.functions as func

from shared import repository
from shared.auth import get_user_oid

bp = func.Blueprint()


def run(job_id: str, user_oid: str, saved: bool) -> dict:
    job = repository.get_job(job_id)
    if job is None:
        return {"status_code": 404, "body": {"error": "Job not found"}}
    if job["user_id"] != user_oid:
        return {"status_code": 403, "body": {"error": "Not authorized to modify this job"}}

    # is_saved is one of the projected fields, so this writes both the canonical
    # job item and the cookbook listing item - see shared/repository.py.
    repository.update_job(job_id, is_saved=saved)

    return {"status_code": 200, "body": {"job_id": job_id, "is_saved": saved}}


@bp.route(route="jobs/{jobId}/save", methods=["PATCH"])
def job_save_http(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    saved = bool(body.get("saved", True))
    outcome = run(req.route_params.get("jobId"), get_user_oid(req), saved)
    return func.HttpResponse(
        json.dumps(outcome["body"]), status_code=outcome["status_code"], mimetype="application/json"
    )
