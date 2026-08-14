import datetime

import azure.durable_functions as df

from shared import config, menu_extraction, repository

bp = df.Blueprint()


def _cache_is_fresh(menu_last_fetched_at: str | None) -> bool:
    """Has this restaurant's menu been fetched within the TTL?

    `menu_last_fetched_at` is an ISO-8601 string with an offset (see
    `repository.utc_now_iso`), so this parses rather than comparing datetimes
    handed back by a driver. A malformed or missing value counts as stale, which
    fails towards re-fetching rather than towards serving nothing.
    """
    if not menu_last_fetched_at:
        return False
    try:
        last_fetched = datetime.datetime.fromisoformat(menu_last_fetched_at)
    except ValueError:
        return False
    if last_fetched.tzinfo is None:
        last_fetched = last_fetched.replace(tzinfo=datetime.timezone.utc)

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=config.menu_cache_ttl_hours()
    )
    return last_fetched > cutoff


def run(activity_input: dict) -> dict:
    restaurant_id = activity_input["restaurant_id"]
    name = activity_input.get("restaurant_name") or restaurant_id
    address = activity_input.get("restaurant_address")
    menu_source_url = activity_input.get("menu_source_url")

    restaurant = repository.get_restaurant(restaurant_id)
    if restaurant and _cache_is_fresh(restaurant.get("menu_last_fetched_at")):
        cached = repository.get_menu_items(restaurant_id)
        if cached:
            return {"restaurant_id": restaurant_id, "items": cached, "source": "cache"}

    try:
        fetched_items = menu_extraction.fetch_menu_items(name, address, menu_source_url)
    except menu_extraction.MenuExtractionError:
        # Graceful degrade rather than propagate: the state machine's catch-all
        # -> mark_job_failed would otherwise fail the whole job over a menu-fetch
        # hiccup, but match_menu_item's VISION_ONLY_MEDIUM outcome already exists
        # to handle "no real menu data available". Leaving menu_last_fetched_at
        # untouched means the next job retries the fetch instead of permanently
        # caching a failure.
        return {"restaurant_id": restaurant_id, "items": [], "source": "fetch_failed"}

    persisted_items = repository.replace_menu_items(restaurant_id, fetched_items)
    repository.mark_menu_fetched(restaurant_id, menu_source_url)
    return {"restaurant_id": restaurant_id, "items": persisted_items, "source": "claude_fetch"}


@bp.activity_trigger(input_name="activityInput")
def fetch_restaurant_menu(activityInput: dict) -> dict:
    return run(activityInput)
