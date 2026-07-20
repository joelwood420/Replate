from unittest.mock import MagicMock

from activities import geocode_restaurant_candidates as geocode


def test_returns_candidates_for_normal_coordinates():
    candidates = geocode._stub_lookup(40.7128, -74.0060)

    assert len(candidates) == 3
    distances = [c["distance_m"] for c in candidates]
    assert distances == sorted(distances)


def test_returns_empty_list_for_null_island_sentinel():
    candidates = geocode._stub_lookup(0.0, 0.0)

    assert candidates == []


def test_persists_candidates_to_job_restaurant_candidates():
    conn = MagicMock()
    candidates = geocode._stub_lookup(40.7128, -74.0060)

    geocode._persist("job-123", candidates, conn)

    insert_calls = [
        call for call in conn.cursor().execute.call_args_list if "JobRestaurantCandidates" in call.args[0]
    ]
    assert len(insert_calls) == len(candidates)


def test_run_skips_db_when_no_candidates_found(monkeypatch):
    monkeypatch.setattr(geocode.db, "get_connection", MagicMock(side_effect=AssertionError("should not connect")))

    result = geocode.run({"job_id": "job-123", "latitude": 0.0, "longitude": 0.0})

    assert result == []
