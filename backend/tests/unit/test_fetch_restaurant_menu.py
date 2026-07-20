from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from activities import fetch_restaurant_menu as fetch_menu


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


def test_refetches_when_cache_missing_or_stale():
    stale = _utcnow_naive() - timedelta(hours=999)
    conn = _mock_conn(fetchone_result=(stale,), fetchall_result=[])

    result = fetch_menu._execute({"restaurant_id": "stub-1", "menu_source_url": "https://x"}, conn)

    assert result["source"] == "stub_fetch"
    assert len(result["items"]) == len(fetch_menu.CANNED_MENUS["stub-1"])


def test_refetches_when_no_prior_fetch_recorded():
    conn = _mock_conn(fetchone_result=(None,), fetchall_result=[])

    result = fetch_menu._execute({"restaurant_id": "stub-3", "menu_source_url": "https://x"}, conn)

    assert result["source"] == "stub_fetch"
    assert len(result["items"]) == len(fetch_menu.CANNED_MENUS["stub-3"])


def test_returns_structured_menu_items_shape():
    conn = _mock_conn(fetchone_result=(None,), fetchall_result=[])

    result = fetch_menu._execute({"restaurant_id": "stub-1", "menu_source_url": "https://x"}, conn)

    for item in result["items"]:
        assert set(item.keys()) == {"menu_item_id", "item_name", "item_description", "price"}
