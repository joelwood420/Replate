"""POST /api/jobs/{jobId}/reverse-engineer - start stage 2 for an identified dish.

This is the only HTTP handler that starts a state machine; the rest just read and
write. Stage 2's input is rebuilt here from what stage 1 persisted, mirroring how
orchestrator_starter_queue.build_orchestration_input works for stage 1.
"""

from shared import config, http, rate_limit, repository, sfn
from shared.auth import get_user_oid
from shared.models import JobStatus

# Stage 1 already claimed the bare job_id as its execution name, and Step Functions
# refuses a name used in the last 90 days - so stage 2 needs its own or the start
# would collide with the completed stage-1 execution.
RECIPE_INSTANCE_SUFFIX = "-recipe"


def _load_job_for_recipe(job_id: str) -> dict | None:
    """Rebuild the stage-2 input from what stage 1 persisted.

    Was a LEFT JOIN across Jobs and JobResults; now two point reads. The vision
    guess is stored as a nested map rather than a JSON string, so there is nothing
    to parse on the way out.
    """
    job = repository.get_job(job_id)
    if job is None:
        return None

    result = repository.get_job_result(job_id) or {}
    return {
        "user_id": job["user_id"],
        "status": job["status"],
        "updated_at": job.get("updated_at"),
        "match_result": {
            "dish_name": result.get("dish_name"),
            "cuisine": result.get("cuisine"),
            "vision_confidence": result.get("confidence"),
            "matched_restaurant_id": result.get("matched_restaurant_id"),
            "matched_menu_item_id": result.get("matched_menu_item_id"),
            "match_confidence": result.get("match_confidence"),
            "match_method": result.get("match_method"),
        },
        "vision_guess": result.get("vision_guess"),
    }


def build_recipe_input(job_id: str, user_oid: str) -> dict:
    """Validate the request and, if it passes, flip the job to Generating.

    Returns either `{"status_code": ..., "body": ...}` to short-circuit, or
    `{"orchestration_input": ...}` for the caller to start the orchestration with.
    """
    job = _load_job_for_recipe(job_id)
    if job is None:
        return {"status_code": 404, "body": {"error": "Job not found"}}
    if job["user_id"] != user_oid:
        return {"status_code": 403, "body": {"error": "Not authorized to modify this job"}}
    if job["status"] != JobStatus.IDENTIFIED:
        # Covers "already generating" and "already has a recipe" in one check.
        return {
            "status_code": 409,
            "body": {
                "error": f"Job is {job['status']}, not {JobStatus.IDENTIFIED} - "
                "nothing to reverse engineer"
            },
        }
    if job["vision_guess"] is None:
        # Only reachable for jobs written before the vision guess was persisted.
        return {
            "status_code": 409,
            "body": {"error": "This dish is missing its vision analysis and cannot be reverse engineered"},
        }

    # Last, after every rejection above: a request that was never going to
    # generate anything should not spend the user's generation quota. This is
    # the heaviest call in the pipeline, hence its own quota separate from
    # scanning - see shared/rate_limit.py.
    quota = rate_limit.check_and_consume(user_oid, rate_limit.Action.RECIPE)
    if not quota["allowed"]:
        return {
            "status_code": 429,
            "body": {"error": quota["error"], "retry_after_seconds": quota["retry_after_seconds"]},
            "headers": {"Retry-After": str(quota["retry_after_seconds"])},
        }

    # Name the execution after the job's *current* Identified state (its updated_at,
    # captured before the flip to Generating below). Two concurrent taps of the same
    # Identified job build the same name and collide - the intended double-tap guard.
    # A genuine retry only happens after a prior attempt reverted the job to
    # Identified with a fresh updated_at, so it gets a new name and actually starts.
    # The old fixed "{job_id}-recipe" name could never restart after any attempt,
    # because Step Functions blocks a reused name for 90 days - so a single failed
    # (or completed) generation left the dish un-retryable and stuck in Generating.
    execution_name = sfn.sanitize_name(f"{job_id}{RECIPE_INSTANCE_SUFFIX}-{job['updated_at']}")

    repository.update_job(job_id, status=JobStatus.GENERATING, error_message=None)

    return {
        "orchestration_input": {
            "job_id": job_id,
            "vision_guess": job["vision_guess"],
            "match_result": job["match_result"],
        },
        "execution_name": execution_name,
    }


def handle_request(job_id: str, user_oid: str) -> dict:
    outcome = build_recipe_input(job_id, user_oid)
    if "orchestration_input" not in outcome:
        return outcome

    # A False return means an execution with this name already exists, i.e. the
    # user double-tapped the button. That is still a 202 - the work is in flight.
    sfn.start_execution(
        config.recipe_state_machine_arn(),
        name=outcome["execution_name"],
        payload=outcome["orchestration_input"],
    )
    return {"status_code": 202, "body": {"job_id": job_id, "status": JobStatus.GENERATING}}


def handler(event, context=None):
    """POST /api/jobs/{jobId}/reverse-engineer"""
    return http.from_outcome(handle_request(http.path_param(event, "jobId"), get_user_oid(event)))
