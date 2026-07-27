from unittest.mock import MagicMock

import pytest

from activities import select_restaurant_candidate as select_candidate


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def test_load_restaurant_returns_none_when_not_found():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None

    assert select_candidate._load_restaurant("missing-id", conn) is None


def test_load_restaurant_shapes_row_with_null_distance():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(
        RestaurantId="place-1",
        Name="Luigi's",
        Address="123 Main St",
        Latitude=40.7,
        Longitude=-74.0,
        MenuSourceUrl=None,
    )

    candidate = select_candidate._load_restaurant("place-1", conn)

    assert candidate == {
        "restaurant_id": "place-1",
        "name": "Luigi's",
        "address": "123 Main St",
        "latitude": 40.7,
        "longitude": -74.0,
        "distance_m": None,
        "menu_source_url": None,
    }


def test_run_raises_when_restaurant_not_found(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    monkeypatch.setattr(select_candidate.db, "get_connection", lambda: _ConnectionCtx(conn))

    with pytest.raises(ValueError, match="place-1"):
        select_candidate.run({"job_id": "job-1", "restaurant_id": "place-1"})


def test_run_happy_path_persists_and_returns_single_candidate(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(
        RestaurantId="place-1",
        Name="Luigi's",
        Address="123 Main St",
        Latitude=40.7,
        Longitude=-74.0,
        MenuSourceUrl=None,
    )
    monkeypatch.setattr(select_candidate.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = select_candidate.run({"job_id": "job-1", "restaurant_id": "place-1"})

    assert result == [
        {
            "restaurant_id": "place-1",
            "name": "Luigi's",
            "address": "123 Main St",
            "latitude": 40.7,
            "longitude": -74.0,
            "distance_m": None,
            "menu_source_url": None,
        }
    ]
    insert_calls = [
        c for c in conn.cursor().execute.call_args_list if "JobRestaurantCandidates" in c.args[0]
    ]
    assert len(insert_calls) == 1
