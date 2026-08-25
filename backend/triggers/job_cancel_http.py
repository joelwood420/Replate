"""POST /api/jobs/{jobId}/cancel - abort an in-flight scan to stop model spend.

The scan (stage 1) is where a menu fetch and the vision call cost money, so a user
who sees a scan dragging can stop it. This stops the identify state machine execution
and marks the job CANCELLED - a normal terminal outcome, not a failure.

Only QUEUED/PROCESSING jobs are cancellable here. A job cancelled while still QUEUED
(enqueued but not yet started) is caught by the starter, which skips a CANCELLED job
rather than starting it. Recipe generation (GENERATING) is a separate, user-initiated
stage and is out of scope for this endpoint for now.
"""

from shared import config, http, repository, sfn
from shared.auth import get_user_oid
from shared.models import JobStatus

_CANCELLABLE = (JobStatus.QUEUED, JobStatus.PROCESSING)


def run(job_id: str, user_oid: str) -> dict:
    job = repository.get_job(job_id)
    if job is None:
        return {"status_code": 404, "body": {"error": "Job not found"}}
    if job["user_id"] != user_oid:
        return {"status_code": 403, "body": {"error": "Not authorized to modify this job"}}
    if job["status"] not in _CANCELLABLE:
        # Already identified, failed, completed or cancelled - nothing in flight to stop.
        return {
            "status_code": 409,
            "body": {"error": f"Job is {job['status']} - there is no scan to cancel"},
        }

    # Stop the running execution, then mark the job. A False return (never started, or
    # already finished in the race window) is fine: the CANCELLED status still stops a
    # QUEUED job at the starter and is the terminal state either way.
    sfn.stop_execution(config.identify_state_machine_arn(), sfn.sanitize_name(job_id))
    repository.update_job(job_id, status=JobStatus.CANCELLED, error_message=None)

    return {"status_code": 200, "body": {"job_id": job_id, "status": JobStatus.CANCELLED}}


def handler(event, context=None):
    """POST /api/jobs/{jobId}/cancel"""
    return http.from_outcome(run(http.path_param(event, "jobId"), get_user_oid(event)))
