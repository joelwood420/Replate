from unittest.mock import MagicMock

from activities import geocode_restaurant_candidates as geocode
from shared import ddb, repository


def test_returns_candidates_for_normal_coordinates():
    candidates = geocode._stub_lookup(40.7128, -74.0060)

    assert len(candidates) == 3
    distances = [c["distance_m"] for c in candidates]
    assert distances == sorted(distances)


def test_returns_empty_list_for_null_island_sentinel():
    candidates = geocode._stub_lookup(0.0, 0.0)

    assert candidates == []


def test_persists_candidates_against_the_job(ddb_table):
    candidates = geocode._stub_lookup(40.7128, -74.0060)

    geocode._persist("job-123", candidates)

    stored = ddb.query_prefix(ddb.job_pk("job-123"), "CANDIDATE#")
    assert len(stored) == len(candidates)


def test_persists_each_candidate_as_a_restaurant(ddb_table):
    """The menu fetch later reads these by restaurant id."""
    candidates = geocode._stub_lookup(40.7128, -74.0060)

    geocode._persist("job-123", candidates)

    for candidate in candidates:
        assert repository.get_restaurant(candidate["restaurant_id"])["name"] == candidate["name"]


def test_persisting_twice_does_not_clobber_a_cached_menu(ddb_table):
    """Re-geocoding must not reset MenuLastFetchedAt and force a re-scrape."""
    candidates = geocode._stub_lookup(40.7128, -74.0060)
    geocode._persist("job-123", candidates)
    repository.mark_menu_fetched(candidates[0]["restaurant_id"], "https://menu")

    geocode._persist("job-456", candidates)

    assert repository.get_restaurant(candidates[0]["restaurant_id"])["menu_last_fetched_at"] is not None


def test_run_skips_persistence_when_no_candidates_found(monkeypatch):
    monkeypatch.setattr(
        geocode.repository, "put_job_candidates", MagicMock(side_effect=AssertionError("should not write"))
    )

    result = geocode.run({"job_id": "job-123", "latitude": 0.0, "longitude": 0.0})

    assert result == []
