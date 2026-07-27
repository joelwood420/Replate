import azure.durable_functions as df

bp = df.Blueprint()

ORCHESTRATOR_NAME = "dish_orchestrator"


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

        query_text = match_result.get("dish_name") or vision_guess.get("dish_name_guess")
        embeddings = yield context.call_activity(
            "query_culinary_embeddings", {"query_text": query_text, "top_k": 5}
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
            "persist_job_result",
            {"job_id": job_input["job_id"], "match_result": match_result, "recreation": recreation},
        )
        return {"job_id": job_input["job_id"], "status": "Completed"}

    except Exception as ex:
        yield context.call_activity(
            "mark_job_failed", {"job_id": job_input["job_id"], "error_message": str(ex)}
        )
        raise


@bp.orchestration_trigger(context_name="context")
def dish_orchestrator_trigger(context: df.DurableOrchestrationContext):
    result = yield from dish_orchestrator(context)
    return result
