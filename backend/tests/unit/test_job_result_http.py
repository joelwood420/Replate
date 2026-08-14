import pytest

from shared import repository
from shared.models import JobStatus, MatchMethod
from triggers import job_result_http

_MATCH_RESULT = {
    "dish_name": "Margherita Pizza",
    "cuisine": "Italian",
    "vision_confidence": 0.8,
    "matched_restaurant_id": "stub-1",
    "matched_menu_item_id": None,
    "match_confidence": 0.9,
    "match_method": MatchMethod.MENU_MATCHED,
}


@pytest.fixture(autouse=True)
def stub_presigned_url(monkeypatch):
    monkeypatch.setattr(job_result_http.storage, "generate_read_url", lambda key: f"{key}?sig=abc")


def _job(status=JobStatus.PROCESSING, owner="owner-oid"):
    return repository.create_job(
        job_id="job-1", user_oid=owner, status=status, image_key="uploads/photo.jpg"
    )


def test_returns_404_for_unknown_job_id(ddb_table):
    result = job_result_http.run("missing-job", "user-oid-1")

    assert result["status_code"] == 404


def test_returns_403_when_oid_does_not_match_job_owner(ddb_table):
    _job()

    result = job_result_http.run("job-1", "different-oid")

    assert result["status_code"] == 403


def test_returns_pending_status_when_not_yet_completed(ddb_table):
    job = _job()

    result = job_result_http.run("job-1", "owner-oid")

    assert result["status_code"] == 200
    assert result["body"]["status"] == JobStatus.PROCESSING
    assert result["body"]["image_url"] == "uploads/photo.jpg?sig=abc"
    assert result["body"]["is_saved"] is False
    assert result["body"]["created_at"] == job["created_at"]
    assert "result" not in result["body"]


def test_created_at_carries_an_explicit_utc_offset(ddb_table):
    """Without one, `new Date(...)` on the client parses it as local time and
    skews every "time ago" display by the viewer's offset."""
    _job()

    created_at = job_result_http.run("job-1", "owner-oid")["body"]["created_at"]

    assert created_at.endswith("+00:00")


def test_returns_full_nested_result_when_completed(ddb_table):
    _job(status=JobStatus.COMPLETED)
    repository.upsert_restaurant("stub-1", "Marchetti", None, None, None, None)
    repository.put_job_result("job-1", _MATCH_RESULT)
    repository.replace_dish_elements(
        "job-1",
        [
            {
                "name": "Crust",
                "description": "desc",
                "role": "Base",
                "sort_order": 0,
                "ingredients": [
                    {"ingredient_name": "Flour", "amount": "2", "unit": "cup", "sort_order": 0}
                ],
                "steps": [{"step_number": 1, "instruction": "Mix."}],
            }
        ],
    )

    result = job_result_http.run("job-1", "owner-oid")

    body = result["body"]
    assert result["status_code"] == 200
    assert body["image_url"] == "uploads/photo.jpg?sig=abc"
    assert body["result"]["dish_name"] == "Margherita Pizza"
    # Was a LEFT JOIN, now an explicit point lookup.
    assert body["result"]["restaurant_name"] == "Marchetti"
    assert len(body["result"]["elements"]) == 1
    assert body["result"]["elements"][0]["name"] == "Crust"
    assert body["result"]["elements"][0]["role"] == "Base"
    assert body["result"]["elements"][0]["ingredients"][0]["ingredient_name"] == "Flour"


def test_returns_result_with_empty_elements_when_identified(ddb_table):
    """Stage 1 output is available before any recipe exists.

    The frontend needs the dish name, restaurant and confidence badge to render the
    "Reverse engineer" screen, so `result` can't wait for status Completed.
    """
    _job(status=JobStatus.IDENTIFIED)
    repository.upsert_restaurant("stub-1", "Marchetti", None, None, None, None)
    repository.put_job_result("job-1", _MATCH_RESULT)

    body = job_result_http.run("job-1", "owner-oid")["body"]

    assert body["status"] == JobStatus.IDENTIFIED
    assert body["result"]["dish_name"] == "Margherita Pizza"
    assert body["result"]["match_method"] == MatchMethod.MENU_MATCHED
    assert body["result"]["elements"] == []


def test_vision_only_result_has_no_restaurant_name(ddb_table):
    _job(status=JobStatus.IDENTIFIED)
    repository.put_job_result(
        "job-1",
        {**_MATCH_RESULT, "matched_restaurant_id": None, "match_method": MatchMethod.VISION_ONLY_LOW},
    )

    body = job_result_http.run("job-1", "owner-oid")["body"]

    assert body["result"]["restaurant_name"] is None
    assert body["result"]["match_method"] == MatchMethod.VISION_ONLY_LOW


def test_surfaces_error_message_on_an_identified_job(ddb_table):
    """A failed reverse-engineer attempt reverts to Identified, not Failed."""
    _job(status=JobStatus.IDENTIFIED)
    repository.put_job_result("job-1", _MATCH_RESULT)
    repository.update_job("job-1", error_message="generator exploded")

    body = job_result_http.run("job-1", "owner-oid")["body"]

    assert body["status"] == JobStatus.IDENTIFIED
    assert body["error_message"] == "generator exploded"
    assert body["result"] is not None


def test_no_error_message_key_when_there_is_no_error(ddb_table):
    _job()

    assert "error_message" not in job_result_http.run("job-1", "owner-oid")["body"]
