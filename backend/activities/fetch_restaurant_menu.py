import uuid
from datetime import datetime, timedelta, timezone

import azure.durable_functions as df

from shared import config, db, menu_extraction

bp = df.Blueprint()


def _execute(activity_input: dict, conn) -> dict:
    restaurant_id = activity_input["restaurant_id"]
    name = activity_input.get("restaurant_name") or restaurant_id
    address = activity_input.get("restaurant_address")
    menu_source_url = activity_input.get("menu_source_url")
    cursor = conn.cursor()

    cursor.execute("SELECT MenuLastFetchedAt FROM Restaurants WHERE RestaurantId = ?", restaurant_id)
    row = cursor.fetchone()
    last_fetched = row[0] if row else None

    if last_fetched is not None:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=config.menu_cache_ttl_hours())
        if last_fetched > cutoff:
            cursor.execute(
                "SELECT MenuItemId, ItemName, ItemDescription, Price FROM MenuItems WHERE RestaurantId = ?",
                restaurant_id,
            )
            cached_rows = cursor.fetchall()
            if cached_rows:
                items = [
                    {
                        "menu_item_id": str(cached.MenuItemId),
                        "item_name": cached.ItemName,
                        "item_description": cached.ItemDescription,
                        "price": cached.Price,
                    }
                    for cached in cached_rows
                ]
                return {"restaurant_id": restaurant_id, "items": items, "source": "cache"}

    try:
        fetched_items = menu_extraction.fetch_menu_items(name, address, menu_source_url)
    except menu_extraction.MenuExtractionError:
        # Graceful degrade rather than propagate: the orchestrator's blanket
        # except -> mark_job_failed would otherwise fail the whole job over a
        # menu-fetch hiccup, but match_menu_item's VISION_ONLY_MEDIUM outcome
        # already exists to handle "no real menu data available". Leaving
        # MenuLastFetchedAt untouched means the next job retries the fetch
        # instead of permanently caching a failure.
        return {"restaurant_id": restaurant_id, "items": [], "source": "fetch_failed"}

    cursor.execute("DELETE FROM MenuItems WHERE RestaurantId = ?", restaurant_id)

    persisted_items = []
    for item in fetched_items:
        menu_item_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO MenuItems (MenuItemId, RestaurantId, ItemName, ItemDescription, Price) "
            "VALUES (?, ?, ?, ?, ?)",
            menu_item_id,
            restaurant_id,
            item["item_name"],
            item["item_description"],
            item["price"],
        )
        persisted_items.append({"menu_item_id": menu_item_id, **item})

    cursor.execute(
        "UPDATE Restaurants SET MenuSourceUrl = ?, MenuLastFetchedAt = SYSUTCDATETIME() WHERE RestaurantId = ?",
        menu_source_url,
        restaurant_id,
    )
    return {"restaurant_id": restaurant_id, "items": persisted_items, "source": "claude_fetch"}


def run(activity_input: dict) -> dict:
    with db.get_connection() as conn:
        return _execute(activity_input, conn)


@bp.activity_trigger(input_name="activityInput")
def fetch_restaurant_menu(activityInput: dict) -> dict:
    return run(activityInput)
