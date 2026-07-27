import azure.durable_functions as df

from shared import db

bp = df.Blueprint()


def _load_restaurant(restaurant_id: str, conn) -> dict | None:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT RestaurantId, Name, Address, Latitude, Longitude, MenuSourceUrl FROM Restaurants "
        "WHERE RestaurantId = ?",
        restaurant_id,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "restaurant_id": row.RestaurantId,
        "name": row.Name,
        "address": row.Address,
        "latitude": float(row.Latitude),
        "longitude": float(row.Longitude),
        # Not meaningful for a manually-selected restaurant - there's no GPS
        # point to measure distance from.
        "distance_m": None,
        "menu_source_url": row.MenuSourceUrl,
    }


def _persist_candidate(job_id: str, candidate: dict, conn) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO JobRestaurantCandidates (JobId, RestaurantId, DistanceM) VALUES (?, ?, ?)",
        job_id,
        candidate["restaurant_id"],
        candidate["distance_m"],
    )


def run(activity_input: dict) -> list[dict]:
    with db.get_connection() as conn:
        candidate = _load_restaurant(activity_input["restaurant_id"], conn)
        if candidate is None:
            raise ValueError(f"Selected restaurant not found: {activity_input['restaurant_id']}")
        _persist_candidate(activity_input["job_id"], candidate, conn)
    return [candidate]


@bp.activity_trigger(input_name="activityInput")
def select_restaurant_candidate(activityInput: dict) -> list[dict]:
    return run(activityInput)
