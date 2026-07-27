from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from activities import fetch_restaurant_menu as fetch_menu
from shared.menu_extraction import MenuExtractionError


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _mock_conn(fetchone_result, fetchall_result):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result
    return conn


def test_uses_cached_menu_when_within_ttl():
    recent = _utcnow_naive() - timedelta(hours=1)
    cached_row = MagicMock(MenuItemId="item-1", ItemName="Pad Thai", ItemDescription="desc", Price="13.00")
    conn = _mock_conn(fetchone_result=(recent,), fetchall_result=[cached_row])

    result = fetch_menu._execute({"restaurant_id": "stub-2", "menu_source_url": "https://x"}, conn)

    assert result["source"] == "cache"
    assert result["items"] == [
        {"menu_item_id": "item-1", "item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}
    ]
    delete_calls = [c for c in conn.cursor().execute.call_args_list if "DELETE" in c.args[0]]
    assert delete_calls == []


def test_refetches_when_cache_missing_or_stale(monkeypatch):
    stale = _utcnow_naive() - timedelta(hours=999)
    conn = _mock_conn(fetchone_result=(stale,), fetchall_result=[])
    fetched = [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: fetched)

    result = fetch_menu._execute(
        {"restaurant_id": "stub-1", "restaurant_name": "Bangkok Kitchen", "menu_source_url": "https://x"}, conn
    )

    assert result["source"] == "claude_fetch"
    assert result["items"] == [{"menu_item_id": result["items"][0]["menu_item_id"], **fetched[0]}]


def test_refetches_when_no_prior_fetch_recorded(monkeypatch):
    conn = _mock_conn(fetchone_result=(None,), fetchall_result=[])
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: [])

    result = fetch_menu._execute({"restaurant_id": "stub-3", "menu_source_url": "https://x"}, conn)

    assert result["source"] == "claude_fetch"
    assert result["items"] == []


def test_menu_extraction_error_degrades_without_touching_menu_items(monkeypatch):
    conn = _mock_conn(fetchone_result=(None,), fetchall_result=[])

    def raise_extraction_error(*args, **kwargs):
        raise MenuExtractionError("boom")

    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", raise_extraction_error)

    result = fetch_menu._execute({"restaurant_id": "stub-1", "menu_source_url": "https://x"}, conn)

    assert result == {"restaurant_id": "stub-1", "items": [], "source": "fetch_failed"}
    delete_calls = [c for c in conn.cursor().execute.call_args_list if "DELETE" in c.args[0]]
    update_calls = [c for c in conn.cursor().execute.call_args_list if "UPDATE Restaurants" in c.args[0]]
    assert delete_calls == []
    assert update_calls == []


def test_returns_structured_menu_items_shape(monkeypatch):
    conn = _mock_conn(fetchone_result=(None,), fetchall_result=[])
    fetched = [{"item_name": "Margherita Pizza", "item_description": "desc", "price": "14.00"}]
    monkeypatch.setattr(fetch_menu.menu_extraction, "fetch_menu_items", lambda *a, **k: fetched)

    result = fetch_menu._execute({"restaurant_id": "stub-1", "menu_source_url": "https://x"}, conn)

    for item in result["items"]:
        assert set(item.keys()) == {"menu_item_id", "item_name", "item_description", "price"}
