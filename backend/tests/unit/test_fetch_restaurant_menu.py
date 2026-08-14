import datetime

import pytest

from activities import fetch_restaurant_menu as fetch_menu
from shared import ddb, repository
from shared.menu_extraction import MenuExtractionError


@pytest.fixture
def restaurant(ddb_table):
    repository.upsert_restaurant("stub-1", "Bangkok Kitchen", "1 Main St", 1.0, 2.0, "https://x")
    return "stub-1"


def _set_fetched_at(restaurant_id, hours_ago):
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours_ago)
    ddb.update(
        ddb.restaurant_pk(restaurant_id), ddb.SK_META, {"menu_last_fetched_at": moment.isoformat()}
    )


def test_uses_cached_menu_when_within_ttl(restaurant, monkeypatch):
    repository.replace_menu_items(
        restaurant, [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    )
    _set_fetched_at(restaurant, hours_ago=1)
    monkeypatch.setattr(
        fetch_menu.menu_extraction,
        "fetch_menu_items",
        lambda *a, **k: pytest.fail("should not re-fetch inside the TTL"),
    )

    result = fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://x"})

    assert result["source"] == "cache"
    assert result["items"][0]["item_name"] == "Pad Thai"


def test_refetches_when_the_cache_is_stale(restaurant, monkeypatch):
    repository.replace_menu_items(
        restaurant, [{"item_name": "Old Item", "item_description": None, "price": None}]
    )
    _set_fetched_at(restaurant, hours_ago=999)
    fetched = [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: fetched)

    result = fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://x"})

    assert result["source"] == "claude_fetch"
    assert [item["item_name"] for item in result["items"]] == ["Pad Thai"]
    # The stale item is replaced, not appended to.
    assert [item["item_name"] for item in repository.get_menu_items(restaurant)] == ["Pad Thai"]


def test_refetches_when_no_prior_fetch_recorded(restaurant, monkeypatch):
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: [])

    result = fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://x"})

    assert result["source"] == "claude_fetch"
    assert result["items"] == []


def test_refetches_when_the_restaurant_is_unknown(ddb_table, monkeypatch):
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: [])

    result = fetch_menu.run({"restaurant_id": "never-seen", "menu_source_url": "https://x"})

    assert result["source"] == "claude_fetch"


def test_a_fresh_timestamp_without_items_still_refetches(restaurant, monkeypatch):
    """An empty cache is not a cache hit - otherwise a restaurant whose first
    fetch returned nothing would serve an empty menu until the TTL expired."""
    _set_fetched_at(restaurant, hours_ago=1)
    monkeypatch.setattr(
        fetch_menu.menu_extraction,
        "fetch_menu_items",
        lambda *a, **k: [{"item_name": "Pad Thai", "item_description": None, "price": None}],
    )

    result = fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://x"})

    assert result["source"] == "claude_fetch"


def test_menu_extraction_error_degrades_without_touching_the_cache(restaurant, monkeypatch):
    """Graceful degrade: match_menu_item's VISION_ONLY_MEDIUM outcome already
    handles "no menu data", and leaving the timestamp alone means the next job
    retries rather than caching the failure."""
    repository.replace_menu_items(
        restaurant, [{"item_name": "Existing", "item_description": None, "price": None}]
    )

    def raise_extraction_error(*args, **kwargs):
        raise MenuExtractionError("boom")

    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", raise_extraction_error)

    result = fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://x"})

    assert result == {"restaurant_id": restaurant, "items": [], "source": "fetch_failed"}
    assert repository.get_restaurant(restaurant)["menu_last_fetched_at"] is None
    assert len(repository.get_menu_items(restaurant)) == 1


def test_returns_structured_menu_items_shape(restaurant, monkeypatch):
    fetched = [{"item_name": "Margherita Pizza", "item_description": "desc", "price": "14.00"}]
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: fetched)

    result = fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://x"})

    for item in result["items"]:
        assert set(item.keys()) == {"menu_item_id", "item_name", "item_description", "price"}


def test_a_successful_fetch_records_the_source_url(restaurant, monkeypatch):
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: [])

    fetch_menu.run({"restaurant_id": restaurant, "menu_source_url": "https://new-menu"})

    stored = repository.get_restaurant(restaurant)
    assert stored["menu_source_url"] == "https://new-menu"
    assert stored["menu_last_fetched_at"] is not None


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_a_missing_or_malformed_timestamp_counts_as_stale(value):
    """Fails towards re-fetching rather than towards serving nothing."""
    assert fetch_menu._cache_is_fresh(value) is False
