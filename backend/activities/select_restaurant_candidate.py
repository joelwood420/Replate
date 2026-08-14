import azure.durable_functions as df

from shared import repository

bp = df.Blueprint()


def _as_candidate(restaurant: dict) -> dict:
    return {
        "restaurant_id": restaurant["restaurant_id"],
        "name": restaurant["name"],
        "address": restaurant.get("address"),
        "latitude": restaurant.get("latitude"),
        "longitude": restaurant.get("longitude"),
        # Not meaningful for a manually-selected restaurant - there's no GPS
        # point to measure distance from.
        "distance_m": None,
        "menu_source_url": restaurant.get("menu_source_url"),
    }


def run(activity_input: dict) -> list[dict]:
    restaurant = repository.get_restaurant(activity_input["restaurant_id"])
    if restaurant is None:
        raise ValueError(f"Selected restaurant not found: {activity_input['restaurant_id']}")

    candidate = _as_candidate(restaurant)
    repository.put_job_candidates(activity_input["job_id"], [candidate])
    return [candidate]


@bp.activity_trigger(input_name="activityInput")
def select_restaurant_candidate(activityInput: dict) -> list[dict]:
    return run(activityInput)
