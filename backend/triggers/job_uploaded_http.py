"""POST /api/jobs/{jobId}/uploaded - the client's signal that its blob PUT finished.

This is what actually starts the pipeline. POST /api/jobs used to enqueue the job
itself, but the client can only upload the photo after that call returns the SAS URL,
so the orchestrator raced the upload and could open the blob before it existed.
Nothing caught it while the vision step was canned and never read the image; image
moderation reads it, and so will the real vision call.

Splitting the two also means an abandoned upload costs nothing: the job simply stays
Queued and no orchestration is ever started.

It is also where the fast food pre-check runs (shared/food_check.py): a photo that is
clearly not food is marked Failed right here, in about a second, instead of after the
full pipeline's vision call - so the diner hears about it before the phone goes away.
"""

from shared import food_check, http, queue, repository
from shared.auth import get_user_oid
from shared.models import NOT_FOOD_MESSAGE, FailureCode, JobStatus


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

    # Only a definite False blocks. None (disabled, unsure, or a service error) falls
    # through to the pipeline, whose vision step still makes the final is_food call.
    if food_check.looks_like_food(job["image_key"]) is False:
        repository.update_job(
            job_id,
            status=JobStatus.FAILED,
            error_message=NOT_FOOD_MESSAGE,
            failure_code=FailureCode.NOT_FOOD,
        )
        repository.remove_from_cookbook(job_id)
        return {
            "status_code": 200,
            "body": {
                "job_id": job_id,
                "status": JobStatus.FAILED,
                "failure_code": FailureCode.NOT_FOOD,
                "error_message": NOT_FOOD_MESSAGE,
            },
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
