from shared import http, repository
from shared.auth import get_user_oid


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


def handler(event, context=None):
    """PATCH /api/jobs/{jobId}/save"""
    saved = bool(http.get_body(event).get("saved", True))
    return http.from_outcome(run(http.path_param(event, "jobId"), get_user_oid(event), saved))
