"""Stage 1 of the pipeline: identify the dish and match it against a real menu.

Runs automatically when a photo is uploaded, and stops at Identified - the dish is
in the user's cookbook with a restaurant, a matched menu item and a confidence
outcome, but no recipe. Recipe generation is stage 2
(`orchestrators/recipe_orchestrator.py`), which the user triggers explicitly, because
it is the heaviest and most expensive call in the pipeline and nobody wants to wait
on it while sitting in the restaurant.
"""

import azure.durable_functions as df

from shared.models import JobStatus

bp = df.Blueprint()


def dish_orchestrator(context: df.DurableOrchestrationContext):
    job_input = context.get_input()

    try:
        vision_task = context.call_activity("vision_guess", {"image_blob_url": job_input["image_blob_url"]})

        if job_input.get("selected_restaurant_id"):
            candidates = yield context.call_activity(
                "select_restaurant_candidate",
                {"job_id": job_input["job_id"], "restaurant_id": job_input["selected_restaurant_id"]},
            )
        else:
            candidates = yield context.call_activity(
                "geocode_restaurant_candidates",
                {
                    "job_id": job_input["job_id"],
                    "latitude": job_input["latitude"],
                    "longitude": job_input["longitude"],
                },
            )

        if candidates:
            top_candidate = candidates[0]
            menu_task = context.call_activity(
                "fetch_restaurant_menu",
                {
                    "restaurant_id": top_candidate["restaurant_id"],
                    "restaurant_name": top_candidate["name"],
                    "restaurant_address": top_candidate["address"],
                    "menu_source_url": top_candidate["menu_source_url"],
                },
            )
            vision_guess, menu_result = yield context.task_all([vision_task, menu_task])
            menu_items = menu_result["items"]
        else:
            top_candidate = None
            menu_items = []
            vision_guess = yield vision_task

        match_result = yield context.call_activity(
            "match_menu_item",
            {
                "vision_guess": vision_guess,
                "menu_items": menu_items,
                "candidate_found": top_candidate is not None,
                "restaurant_id": top_candidate["restaurant_id"] if top_candidate else None,
            },
        )

        # vision_guess is persisted alongside the match so stage 2 can use it as
        # input - nothing else in the schema records it until a recipe exists.
        yield context.call_activity(
            "persist_match_result",
            {
                "job_id": job_input["job_id"],
                "match_result": match_result,
                "vision_guess": vision_guess,
            },
        )
        return {"job_id": job_input["job_id"], "status": JobStatus.IDENTIFIED}

    except Exception as ex:
        yield context.call_activity(
            "mark_job_failed", {"job_id": job_input["job_id"], "error_message": str(ex)}
        )
        raise


@bp.orchestration_trigger(context_name="context")
def dish_orchestrator_trigger(context: df.DurableOrchestrationContext):
    result = yield from dish_orchestrator(context)
    return result
