from unittest.mock import MagicMock

from activities import geocode_restaurant_candidates as geocode
from shared import anthropic_client, ddb, places, repository


def _candidate(rid="osm-node-1", name="Trattoria Roma", distance=55):
    """A candidate in the shape the OSM/Claude providers return and _persist consumes."""
    return {
        "restaurant_id": rid,
        "name": name,
        "address": "10 Sample Ave",
        "latitude": 40.71,
        "longitude": -74.00,
        "distance_m": distance,
        "menu_source_url": "https://example.com/menu",
    }


def test_run_returns_and_persists_provider_candidates(monkeypatch, ddb_table):
    found = [_candidate("osm-node-1", "A", 55), _candidate("osm-node-2", "B", 140)]
    monkeypatch.setattr(places, "nearby_restaurants", lambda lat, lon: found)

    result = geocode.run({"job_id": "job-123", "latitude": 40.7128, "longitude": -74.0060})

    assert result == found
    assert len(ddb.query_prefix(ddb.job_pk("job-123"), "CANDIDATE#")) == 2


def test_run_short_circuits_on_null_island(monkeypatch):
    """(0, 0) means no usable GPS, so no provider call and no write."""
    monkeypatch.setattr(
        places, "nearby_restaurants", MagicMock(side_effect=AssertionError("should not call"))
    )
    monkeypatch.setattr(
        geocode.repository, "put_job_candidates", MagicMock(side_effect=AssertionError("no write"))
    )

    assert geocode.run({"job_id": "job-123", "latitude": 0.0, "longitude": 0.0}) == []


def test_run_falls_back_to_claude_when_overpass_finds_nothing(monkeypatch, ddb_table):
    monkeypatch.setattr(places, "nearby_restaurants", lambda lat, lon: [])
    monkeypatch.setattr(geocode, "_claude_nearby", lambda lat, lon: [_candidate("claude-abc", "Fallback Diner", None)])

    result = geocode.run({"job_id": "job-9", "latitude": 40.7, "longitude": -74.0})

    assert result[0]["restaurant_id"] == "claude-abc"
    assert repository.get_restaurant("claude-abc")["name"] == "Fallback Diner"


def test_run_falls_back_to_claude_when_overpass_errors(monkeypatch, ddb_table):
    def boom(lat, lon):
        raise places.PlacesError("overpass down")

    monkeypatch.setattr(places, "nearby_restaurants", boom)
    monkeypatch.setattr(geocode, "_claude_nearby", lambda lat, lon: [_candidate("claude-x", "X", None)])

    result = geocode.run({"job_id": "job-10", "latitude": 40.7, "longitude": -74.0})

    assert [c["restaurant_id"] for c in result] == ["claude-x"]


def test_run_returns_empty_when_both_providers_find_nothing(monkeypatch):
    monkeypatch.setattr(places, "nearby_restaurants", lambda lat, lon: [])
    monkeypatch.setattr(geocode, "_claude_nearby", lambda lat, lon: [])
    monkeypatch.setattr(
        geocode.repository, "put_job_candidates", MagicMock(side_effect=AssertionError("no write"))
    )

    assert geocode.run({"job_id": "job-11", "latitude": 40.7, "longitude": -74.0}) == []


def test_persist_stores_candidates_and_restaurants(ddb_table):
    candidates = [_candidate("osm-node-1", "A", 55), _candidate("osm-node-2", "B", 140)]

    geocode._persist("job-123", candidates)

    assert len(ddb.query_prefix(ddb.job_pk("job-123"), "CANDIDATE#")) == len(candidates)
    for candidate in candidates:
        assert repository.get_restaurant(candidate["restaurant_id"])["name"] == candidate["name"]


def test_persisting_twice_does_not_clobber_a_cached_menu(ddb_table):
    """Re-geocoding must not reset MenuLastFetchedAt and force a re-scrape."""
    candidates = [_candidate("osm-node-1", "A", 55)]
    geocode._persist("job-123", candidates)
    repository.mark_menu_fetched(candidates[0]["restaurant_id"], "https://menu")

    geocode._persist("job-456", candidates)

    assert repository.get_restaurant(candidates[0]["restaurant_id"])["menu_last_fetched_at"] is not None


def test_claude_nearby_parses_web_search_json(monkeypatch):
    monkeypatch.setattr(geocode.config, "anthropic_menu_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(anthropic_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        anthropic_client,
        "web_search_completion",
        lambda **kwargs: '{"restaurants": [{"name": "Real Diner", "address": "1 St", '
        '"latitude": 1.0, "longitude": 2.0, "website": "https://d"}]}',
    )

    result = geocode._claude_nearby(40.7, -74.0)

    assert len(result) == 1
    assert result[0]["name"] == "Real Diner"
    assert result[0]["restaurant_id"].startswith("claude-")
    assert result[0]["menu_source_url"] == "https://d"


def test_claude_nearby_returns_empty_when_not_configured(monkeypatch):
    monkeypatch.setattr(geocode.config, "anthropic_menu_model", lambda: "")

    assert geocode._claude_nearby(40.7, -74.0) == []
