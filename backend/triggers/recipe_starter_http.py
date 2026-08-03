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

from shared import db
from shared.auth import get_user_oid
from shared.models import JobStatus

bp = df.Blueprint()

# Stage 1 already claimed the bare job_id as its orchestration instance id, so stage 2
# needs its own or Durable will refuse to start / collide with the completed instance.
RECIPE_INSTANCE_SUFFIX = ":recipe"


def _load_job_for_recipe(job_id: str, conn) -> dict | None:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT j.UserId, j.Status, r.DishName, r.Cuisine, r.Confidence, r.MatchedRestaurantId, "
        "r.MatchedMenuItemId, r.MatchConfidence, r.MatchMethod, r.VisionGuessJson "
        "FROM Jobs j LEFT JOIN JobResults r ON r.JobId = j.JobId WHERE j.JobId = ?",
        job_id,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "user_id": str(row.UserId),
        "status": row.Status,
        "match_result": {
            "dish_name": row.DishName,
            "cuisine": row.Cuisine,
            "vision_confidence": row.Confidence,
            "matched_restaurant_id": row.MatchedRestaurantId,
            "matched_menu_item_id": str(row.MatchedMenuItemId) if row.MatchedMenuItemId else None,
            "match_confidence": row.MatchConfidence,
            "match_method": row.MatchMethod,
        },
        "vision_guess": json.loads(row.VisionGuessJson) if row.VisionGuessJson else None,
    }


def _mark_generating(job_id: str, conn) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Jobs SET Status = ?, ErrorMessage = NULL, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.GENERATING,
        job_id,
    )


def build_recipe_input(job_id: str, user_oid: str) -> dict:
    """Validate the request and, if it passes, flip the job to Generating.

    Returns either `{"status_code": ..., "body": ...}` to short-circuit, or
    `{"orchestration_input": ...}` for the caller to start the orchestration with.
    """
    with db.get_connection() as conn:
        job = _load_job_for_recipe(job_id, conn)
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
            # Only reachable for rows written before VisionGuessJson existed.
            return {
                "status_code": 409,
                "body": {"error": "This dish is missing its vision analysis and cannot be reverse engineered"},
            }

        _mark_generating(job_id, conn)

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
        json.dumps(outcome["body"]), status_code=outcome["status_code"], mimetype="application/json"
    )
