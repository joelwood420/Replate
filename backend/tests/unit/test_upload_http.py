import datetime

import pytest

from shared import ddb, repository
from triggers import upload_http

_OWNER = "user-oid-1"


@pytest.fixture(autouse=True)
def stub_presigned_url(monkeypatch):
    monkeypatch.setattr(
        upload_http.blob,
        "generate_upload_sas_url",
        lambda: {"blob_url": "uploads/blob.jpg", "sas_url": "https://x/uploads/blob.jpg?sig=abc"},
    )


def _seed_quota(action, hours_ago, count):
    bucket = (
        datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
        - datetime.timedelta(hours=hours_ago)
    )
    ddb.put(
        {
            "PK": ddb.rate_pk(_OWNER),
            "SK": ddb.rate_sk(action, bucket.strftime("%Y-%m-%dT%H")),
            "call_count": count,
            "expires_at": int((bucket + datetime.timedelta(hours=26)).timestamp()),
        }
    )


def test_generates_upload_url_and_creates_the_job(ddb_table):
    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    assert result["status_code"] == 201
    assert result["body"]["blob_url"] == "uploads/blob.jpg"
    assert result["body"]["upload_url"] == "https://x/uploads/blob.jpg?sig=abc"

    job = repository.get_job(result["body"]["job_id"])
    assert job["user_id"] == _OWNER
    assert job["latitude"] == pytest.approx(40.7)


def test_creates_the_user_profile(ddb_table):
    upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    assert ddb.get(ddb.user_pk(_OWNER), ddb.SK_PROFILE) is not None


def test_does_not_queue_the_job(ddb_table):
    """The client signals upload completion separately - see triggers/job_uploaded_http.py.

    Enqueuing here would race the client's PUT, which only happens after this call
    returns the upload URL.
    """
    assert not hasattr(upload_http, "queue")

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    assert repository.get_job(result["body"]["job_id"])["status"] == "Queued"


def test_returns_400_on_missing_required_fields(ddb_table):
    result = upload_http.run({}, _OWNER)

    assert result["status_code"] == 400
    assert "error" in result["body"]


def test_returns_400_when_both_gps_and_selected_restaurant_present(ddb_table):
    body = {
        "latitude": 1.0,
        "longitude": 2.0,
        "selected_restaurant": {"place_id": "p1", "name": "Luigi's", "latitude": 1.0, "longitude": 2.0},
    }

    assert upload_http.run(body, _OWNER)["status_code"] == 400


def test_returns_400_when_selected_restaurant_missing_required_field(ddb_table):
    body = {"selected_restaurant": {"place_id": "p1", "name": "Luigi's", "latitude": 1.0}}

    assert upload_http.run(body, _OWNER)["status_code"] == 400


def test_selected_restaurant_creates_job_and_restaurant(ddb_table):
    body = {
        "selected_restaurant": {
            "place_id": "place-1",
            "name": "Luigi's",
            "address": "123 Main St",
            "latitude": 40.7,
            "longitude": -74.0,
        }
    }

    result = upload_http.run(body, _OWNER)

    assert result["status_code"] == 201
    assert repository.get_job(result["body"]["job_id"])["selected_restaurant_id"] == "place-1"
    assert repository.get_restaurant("place-1")["name"] == "Luigi's"


def test_returns_429_with_retry_after_when_hourly_quota_is_spent(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "3")
    _seed_quota("scan", 0, 3)

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    assert result["status_code"] == 429
    assert result["headers"]["Retry-After"] == str(result["body"]["retry_after_seconds"])
    assert result["body"]["retry_after_seconds"] > 0
    assert "3 scans" in result["body"]["error"]


def test_throttled_request_creates_no_job(ddb_table, monkeypatch):
    """The quota check has to come before the write, or it caps nothing."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    _seed_quota("scan", 0, 1)

    upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    assert repository.list_jobs(_OWNER) == []


def test_daily_quota_blocks_even_when_the_current_hour_is_clear(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "12")
    for hours_ago in (1, 2, 3):
        _seed_quota("scan", hours_ago, 4)

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    assert result["status_code"] == 429
    assert "12 scans" in result["body"]["error"]
    assert "per day" in result["body"]["error"]


def test_quota_can_be_disabled(ddb_table, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    _seed_quota("scan", 0, 99)

    assert upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)["status_code"] == 201


def test_a_successful_scan_consumes_one_unit(ddb_table):
    upload_http.run({"latitude": 40.7, "longitude": -74.0}, _OWNER)

    rows = ddb.query_prefix(ddb.rate_pk(_OWNER), "scan#")
    assert sum(row["call_count"] for row in rows) == 1
