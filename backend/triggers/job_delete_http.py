from shared import http, repository
from shared.auth import get_user_oid
from shared.models import JobStatus

# A scan that is still running owns a Step Functions execution; deleting the job out from
# under it would orphan that execution (and it could re-create partial rows as it finishes).
# Stopping a live scan is what Cancel is for, so delete only terminal jobs.
IN_FLIGHT = {JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.GENERATING}


def run(job_id: str, user_oid: str) -> dict:
    job = repository.get_job(job_id)
    if job is None:
        return {"status_code": 404, "body": {"error": "Job not found"}}
    if job["user_id"] != user_oid:
        return {"status_code": 403, "body": {"error": "Not authorized to modify this job"}}
    if job["status"] in IN_FLIGHT:
        return {"status_code": 409, "body": {"error": "Cancel this scan before deleting it"}}

    repository.delete_job(job_id)
    return {"status_code": 200, "body": {"job_id": job_id, "deleted": True}}


def handler(event, context=None):
    """DELETE /api/jobs/{jobId}"""
    return http.from_outcome(run(http.path_param(event, "jobId"), get_user_oid(event)))
