"""POST /api/jobs/{jobId}/uploaded - the client's signal that its blob PUT finished.

This is what actually starts the pipeline. POST /api/jobs used to enqueue the job
itself, but the client can only upload the photo after that call returns the SAS URL,
so the orchestrator raced the upload and could open the blob before it existed.
Nothing caught it while the vision step was canned and never read the image; image
moderation reads it, and so will the real vision call.

Splitting the two also means an abandoned upload costs nothing: the job simply stays
Queued and no orchestration is ever started.
"""

import json

import azure.functions as func

from shared import db, queue
from shared.auth import get_user_oid
from shared.models import JobStatus

bp = func.Blueprint()


def _fetch_job(job_id: str, conn) -> dict | None:
    cursor = conn.cursor()
    cursor.execute("SELECT UserId, Status FROM Jobs WHERE JobId = ?", job_id)
    row = cursor.fetchone()
    if row is None:
        return None
    return {"user_id": str(row.UserId), "status": row.Status}


def run(job_id: str, user_oid: str) -> dict:
    with db.get_connection() as conn:
        job = _fetch_job(job_id, conn)
        if job is None:
            return {"status_code": 404, "body": {"error": "Job not found"}}
        if job["user_id"] != user_oid:
            return {"status_code": 403, "body": {"error": "Not authorized to modify this job"}}
        if job["status"] != JobStatus.QUEUED:
            # Covers a retried or duplicated call: only a job still waiting on its
            # photo can be started.
            return {
                "status_code": 409,
                "body": {"error": f"Job is already {job['status']} - its photo was already submitted"},
            }

    # Outside the transaction on purpose - a queue round-trip should not be holding
    # database locks. The status check above is not atomic with this send, so two
    # simultaneous calls could both enqueue; orchestrator_starter_queue starts the
    # orchestration with instance_id=job_id, and Durable rejects a second start for
    # an id that is already running, so a duplicate message cannot double-process.
    queue.send_job_message(job_id)

    return {"status_code": 202, "body": {"job_id": job_id, "status": JobStatus.QUEUED}}


@bp.route(route="jobs/{jobId}/uploaded", methods=["POST"])
def job_uploaded_http(req: func.HttpRequest) -> func.HttpResponse:
    outcome = run(req.route_params.get("jobId"), get_user_oid(req))
    return func.HttpResponse(
        json.dumps(outcome["body"]), status_code=outcome["status_code"], mimetype="application/json"
    )
