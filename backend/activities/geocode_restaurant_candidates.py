import azure.durable_functions as df

from shared import db, restaurants

bp = df.Blueprint()

NULL_ISLAND = (0.0, 0.0)

CANNED_CANDIDATES = [
    {
        "restaurant_id": "stub-1",
        "name": "Trattoria Roma",
        "delta": 0.0005,
        "distance_m": 55,
        "menu_source_url": "https://example.com/menus/stub-1",
    },
    {
        "restaurant_id": "stub-2",
        "name": "Bangkok Kitchen",
        "delta": 0.0012,
        "distance_m": 140,
        "menu_source_url": "https://example.com/menus/stub-2",
    },
    {
        "restaurant_id": "stub-3",
        "name": "The Burger Joint",
        "delta": 0.0020,
        "distance_m": 230,
        "menu_source_url": "https://example.com/menus/stub-3",
    },
]


def _stub_lookup(latitude: float, longitude: float) -> list[dict]:
    if (latitude, longitude) == NULL_ISLAND:
        return []

    candidates = []
    for entry in CANNED_CANDIDATES:
        candidates.append(
            {
                "restaurant_id": entry["restaurant_id"],
                "name": entry["name"],
                "address": f"{100 + entry['distance_m']} Sample Ave",
                "latitude": round(latitude + entry["delta"], 6),
                "longitude": round(longitude + entry["delta"], 6),
                "distance_m": entry["distance_m"],
                "menu_source_url": entry["menu_source_url"],
            }
        )
    return sorted(candidates, key=lambda c: c["distance_m"])


def _persist(job_id: str, candidates: list[dict], conn) -> None:
    cursor = conn.cursor()
    for candidate in candidates:
        restaurants.upsert_restaurant(
            candidate["restaurant_id"],
            candidate["name"],
            candidate["address"],
            candidate["latitude"],
            candidate["longitude"],
            candidate["menu_source_url"],
            conn,
        )
        cursor.execute(
            "INSERT INTO JobRestaurantCandidates (JobId, RestaurantId, DistanceM) VALUES (?, ?, ?)",
            job_id,
            candidate["restaurant_id"],
            candidate["distance_m"],
        )


def run(activity_input: dict) -> list[dict]:
    candidates = _stub_lookup(activity_input["latitude"], activity_input["longitude"])
    if candidates:
        with db.get_connection() as conn:
            _persist(activity_input["job_id"], candidates, conn)
    return candidates


@bp.activity_trigger(input_name="activityInput")
def geocode_restaurant_candidates(activityInput: dict) -> list[dict]:
    return run(activityInput)
