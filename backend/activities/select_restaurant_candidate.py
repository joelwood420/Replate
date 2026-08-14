from shared import models, repository


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


def handler(event, context=None):
    """Lambda entry point for the SelectRestaurantCandidate task.

    Emits the same envelope as the geocode path so the state machine's Choice
    state does not have to care which branch produced the candidate.
    """
    return models.candidate_envelope(run(event))
