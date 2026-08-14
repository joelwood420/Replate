"""POST /api/jobs/{jobId}/reverse-engineer - start stage 2 for an identified dish.

Uses a Durable Functions blueprint rather than the plain func.Blueprint() the other
HTTP triggers use, because only the former can inject a durable client to start an
orchestration.

The stage-2 orchestrator's input is rebuilt here from the stage-1 row already in the
database, mirroring how orchestrator_starter_queue.build_orchestration_input works for
stage 1.
"""

import json

import azure.durable_functions as df
import azure.functions as func

from shared import rate_limit, repository
from shared.auth import get_user_oid
from shared.models import JobStatus

bp = df.Blueprint()

# Stage 1 already claimed the bare job_id as its execution name, so stage 2 needs its
# own or the start call will collide with the completed stage-1 execution.
RECIPE_INSTANCE_SUFFIX = ":recipe"


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

    repository.update_job(job_id, status=JobStatus.GENERATING, error_message=None)

    return {
        "orchestration_input": {
            "job_id": job_id,
            "vision_guess": job["vision_guess"],
            "match_result": job["match_result"],
        }
    }


async def handle_request(job_id: str, user_oid: str, client) -> dict:
    outcome = build_recipe_input(job_id, user_oid)
    if "orchestration_input" in outcome:
        await client.start_new(
            "recipe_orchestrator_trigger",
            instance_id=f"{job_id}{RECIPE_INSTANCE_SUFFIX}",
            client_input=outcome["orchestration_input"],
        )
        return {"status_code": 202, "body": {"job_id": job_id, "status": JobStatus.GENERATING}}
    return outcome


@bp.route(route="jobs/{jobId}/reverse-engineer", methods=["POST"])
@bp.durable_client_input(client_name="client")
async def recipe_starter_http(req: func.HttpRequest, client) -> func.HttpResponse:
    outcome = await handle_request(req.route_params.get("jobId"), get_user_oid(req), client)
    return func.HttpResponse(
        json.dumps(outcome["body"]),
        status_code=outcome["status_code"],
        mimetype="application/json",
        headers=outcome.get("headers"),
    )
