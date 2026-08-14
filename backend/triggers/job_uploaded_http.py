"""POST /api/jobs/{jobId}/uploaded - the client's signal that its blob PUT finished.

This is what actually starts the pipeline. POST /api/jobs used to enqueue the job
itself, but the client can only upload the photo after that call returns the SAS URL,
so the orchestrator raced the upload and could open the blob before it existed.
Nothing caught it while the vision step was canned and never read the image; image
moderation reads it, and so will the real vision call.

Splitting the two also means an abandoned upload costs nothing: the job simply stays
Queued and no orchestration is ever started.
"""

from shared import http, queue, repository
from shared.auth import get_user_oid
from shared.models import JobStatus


def run(job_id: str, user_oid: str) -> dict:
    job = repository.get_job(job_id)
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

    # The status check above is not atomic with this send, so two simultaneous calls
    # could both enqueue. The starter names the execution after the job id, and
    # Step Functions rejects a second execution with a name already in flight, so a
    # duplicate message cannot double-process.
    queue.send_job_message(job_id)

    return {"status_code": 202, "body": {"job_id": job_id, "status": JobStatus.QUEUED}}


def handler(event, context=None):
    """POST /api/jobs/{jobId}/uploaded"""
    return http.from_outcome(run(http.path_param(event, "jobId"), get_user_oid(event)))
