import json

import azure.functions as func

from shared import db
from shared.auth import get_user_oid

bp = func.Blueprint()


def _fetch_owner(job_id: str, conn) -> str | None:
    cursor = conn.cursor()
    cursor.execute("SELECT UserId FROM Jobs WHERE JobId = ?", job_id)
    row = cursor.fetchone()
    return str(row.UserId) if row else None


def run(job_id: str, user_oid: str, saved: bool) -> dict:
    with db.get_connection() as conn:
        owner = _fetch_owner(job_id, conn)
        if owner is None:
            return {"status_code": 404, "body": {"error": "Job not found"}}
        if owner != user_oid:
            return {"status_code": 403, "body": {"error": "Not authorized to modify this job"}}

        cursor = conn.cursor()
        cursor.execute("UPDATE Jobs SET IsSaved = ? WHERE JobId = ?", 1 if saved else 0, job_id)

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
