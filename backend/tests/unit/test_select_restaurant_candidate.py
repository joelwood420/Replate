import pytest

from activities import select_restaurant_candidate as select_candidate
from shared import ddb, repository


def test_run_raises_when_restaurant_not_found(ddb_table):
    with pytest.raises(ValueError, match="place-1"):
        select_candidate.run({"job_id": "job-1", "restaurant_id": "place-1"})


def test_run_happy_path_persists_and_returns_single_candidate(ddb_table):
    repository.upsert_restaurant("place-1", "Luigi's", "123 Main St", 40.7, -74.0, None)

    result = select_candidate.run({"job_id": "job-1", "restaurant_id": "place-1"})

    assert result == [
        {
            "restaurant_id": "place-1",
            "name": "Luigi's",
            "address": "123 Main St",
            "latitude": 40.7,
            "longitude": -74.0,
            # No GPS point to measure from when the user picked the restaurant.
            "distance_m": None,
            "menu_source_url": None,
        }
    ]


def test_run_records_the_candidate_against_the_job(ddb_table):
    repository.upsert_restaurant("place-1", "Luigi's", "123 Main St", 40.7, -74.0, None)

    select_candidate.run({"job_id": "job-1", "restaurant_id": "place-1"})

    candidates = ddb.query_prefix(ddb.job_pk("job-1"), "CANDIDATE#")
    assert [candidate["restaurant_id"] for candidate in candidates] == ["place-1"]


def test_menu_source_url_is_carried_through(ddb_table):
    """The menu fetch downstream uses it as a starting point."""
    repository.upsert_restaurant("place-2", "Trattoria", "9 Side St", 1.0, 2.0, "https://menu")

    result = select_candidate.run({"job_id": "job-2", "restaurant_id": "place-2"})

    assert result[0]["menu_source_url"] == "https://menu"
