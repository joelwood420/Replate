import datetime
from unittest.mock import MagicMock

from triggers import upload_http


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


class _CounterRow:
    """Stands in for a RateLimitCounters row as pyodbc returns it."""

    def __init__(self, window_start, call_count):
        self.WindowStart = window_start
        self.CallCount = call_count


def _current_bucket():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)


def _mock_conn(counter_rows=()):
    """A connection whose rate-limit SELECT returns `counter_rows`.

    The real rate limiter runs against it rather than being stubbed out, so these
    tests cover the quota wiring as well as the endpoint.
    """
    conn = MagicMock()
    conn.cursor().fetchall.return_value = list(counter_rows)
    return conn


def _patch_deps(monkeypatch, conn):
    monkeypatch.setattr(
        upload_http.blob,
        "generate_upload_sas_url",
        lambda: {"blob_url": "https://x/blob", "sas_url": "https://x/blob?sig=abc"},
    )
    monkeypatch.setattr(upload_http.db, "get_connection", lambda: _ConnectionCtx(conn))


def test_generates_sas_url_and_creates_job_row(monkeypatch):
    conn = _mock_conn()
    _patch_deps(monkeypatch, conn)

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    assert result["status_code"] == 201
    assert result["body"]["blob_url"] == "https://x/blob"
    assert result["body"]["upload_url"] == "https://x/blob?sig=abc"
    assert "job_id" in result["body"]

    insert_calls = [c for c in conn.cursor().execute.call_args_list if "INSERT INTO Jobs" in c.args[0]]
    assert len(insert_calls) == 1


def test_does_not_queue_the_job(monkeypatch):
    """The client signals upload completion separately - see triggers/job_uploaded_http.py.

    Enqueuing here would race the client's blob PUT, which only happens after this
    call returns the SAS URL.
    """
    assert not hasattr(upload_http, "queue")

    conn = _mock_conn()
    _patch_deps(monkeypatch, conn)

    upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    queries = [c.args[0] for c in conn.cursor().execute.call_args_list]
    assert any("INSERT INTO Jobs" in q for q in queries)


def test_returns_400_on_missing_required_fields():
    result = upload_http.run({}, "user-oid-1")

    assert result["status_code"] == 400
    assert "error" in result["body"]


def test_returns_400_when_both_gps_and_selected_restaurant_present():
    body = {
        "latitude": 1.0,
        "longitude": 2.0,
        "selected_restaurant": {"place_id": "p1", "name": "Luigi's", "latitude": 1.0, "longitude": 2.0},
    }
    result = upload_http.run(body, "user-oid-1")

    assert result["status_code"] == 400


def test_returns_400_when_selected_restaurant_missing_required_field():
    body = {"selected_restaurant": {"place_id": "p1", "name": "Luigi's", "latitude": 1.0}}
    result = upload_http.run(body, "user-oid-1")

    assert result["status_code"] == 400


def test_selected_restaurant_creates_job_with_selected_restaurant_id(monkeypatch):
    conn = _mock_conn()
    _patch_deps(monkeypatch, conn)

    upserted = []
    monkeypatch.setattr(
        upload_http.restaurants,
        "upsert_restaurant",
        lambda *args, **kwargs: upserted.append(args),
    )

    body = {
        "selected_restaurant": {
            "place_id": "place-1",
            "name": "Luigi's",
            "address": "123 Main St",
            "latitude": 40.7,
            "longitude": -74.0,
        }
    }
    result = upload_http.run(body, "user-oid-1")

    assert result["status_code"] == 201
    assert len(upserted) == 1
    assert upserted[0][0] == "place-1"

    insert_calls = [c for c in conn.cursor().execute.call_args_list if "INSERT INTO Jobs" in c.args[0]]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[-1] == "place-1"  # SelectedRestaurantId is the last bound param


def test_returns_429_with_retry_after_when_hourly_quota_is_spent(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "3")
    conn = _mock_conn([_CounterRow(_current_bucket(), 3)])
    _patch_deps(monkeypatch, conn)

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    assert result["status_code"] == 429
    assert result["headers"]["Retry-After"] == str(result["body"]["retry_after_seconds"])
    assert result["body"]["retry_after_seconds"] > 0
    assert "3 scans" in result["body"]["error"]


def test_throttled_request_creates_no_job(monkeypatch):
    """The quota check has to come before the INSERT, or it caps nothing."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    conn = _mock_conn([_CounterRow(_current_bucket(), 1)])
    _patch_deps(monkeypatch, conn)

    upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    queries = [c.args[0] for c in conn.cursor().execute.call_args_list]
    assert not any("INSERT INTO Jobs" in q for q in queries)
    assert not any("MERGE RateLimitCounters" in q for q in queries)


def test_daily_quota_blocks_even_when_the_current_hour_is_clear(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "12")
    bucket = _current_bucket()
    earlier = [_CounterRow(bucket - datetime.timedelta(hours=n), 4) for n in (1, 2, 3)]
    conn = _mock_conn(earlier)
    _patch_deps(monkeypatch, conn)

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    assert result["status_code"] == 429
    assert "12 scans" in result["body"]["error"]
    assert "per day" in result["body"]["error"]


def test_quota_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    conn = _mock_conn([_CounterRow(_current_bucket(), 99)])
    _patch_deps(monkeypatch, conn)

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    assert result["status_code"] == 201
