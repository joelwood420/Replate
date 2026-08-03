"""Stage 2 of the pipeline: generate the method to recreate an identified dish.

Only runs when the user opens a dish in their cookbook and presses "Reverse
engineer" (`triggers/recipe_starter_http.py`), because this is the heaviest-output
and most expensive part of the pipeline - see docs/decisions.md.

Input is built by that trigger from the stage-1 result already in the database:
`{job_id, vision_guess, match_result}`.

On failure the job goes back to Identified rather than Failed, so a transient
generator error doesn't throw away a good restaurant identification and menu match.
"""

import azure.durable_functions as df

from shared.models import JobStatus

bp = df.Blueprint()


def recipe_orchestrator(context: df.DurableOrchestrationContext):
    job_input = context.get_input()

    try:
        vision_guess = job_input["vision_guess"]
        match_result = job_input["match_result"]

        # top_k is left to the activity, which defaults it from VECTOR_SEARCH_TOP_K.
        # Reading config here would put an env-var read inside a replayed orchestrator.
        query_text = match_result.get("dish_name") or vision_guess.get("dish_name_guess")
        embeddings = yield context.call_activity(
            "query_culinary_embeddings", {"query_text": query_text}
        )

        recreation = yield context.call_activity(
            "generate_recreation",
            {
                "matched_menu_item": match_result,
                "vision_guess": vision_guess,
                "embeddings_context": embeddings,
            },
        )

        yield context.call_activity(
            "persist_recipe_result",
            {"job_id": job_input["job_id"], "recreation": recreation},
        )
        return {"job_id": job_input["job_id"], "status": JobStatus.COMPLETED}

    except Exception as ex:
        yield context.call_activity(
            "mark_recipe_failed", {"job_id": job_input["job_id"], "error_message": str(ex)}
        )
        raise


@bp.orchestration_trigger(context_name="context")
def recipe_orchestrator_trigger(context: df.DurableOrchestrationContext):
    result = yield from recipe_orchestrator(context)
    return result
