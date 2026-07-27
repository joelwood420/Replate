from unittest.mock import MagicMock

from triggers import upload_http


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def test_generates_sas_url_creates_job_row_and_queues_message(monkeypatch):
    monkeypatch.setattr(
        upload_http.blob,
        "generate_upload_sas_url",
        lambda: {"blob_url": "https://x/blob", "sas_url": "https://x/blob?sig=abc"},
    )
    sent_job_ids = []
    monkeypatch.setattr(upload_http.queue, "send_job_message", lambda job_id: sent_job_ids.append(job_id))

    conn = MagicMock()
    monkeypatch.setattr(upload_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = upload_http.run({"latitude": 40.7, "longitude": -74.0}, "user-oid-1")

    assert result["blob_url"] == "https://x/blob"
    assert result["upload_url"] == "https://x/blob?sig=abc"
    assert "job_id" in result
    assert sent_job_ids == [result["job_id"]]

    insert_calls = [c for c in conn.cursor().execute.call_args_list if "INSERT INTO Jobs" in c.args[0]]
    assert len(insert_calls) == 1


def test_returns_error_on_missing_required_fields():
    result = upload_http.run({}, "user-oid-1")

    assert "error" in result


def test_returns_error_when_both_gps_and_selected_restaurant_present():
    body = {
        "latitude": 1.0,
        "longitude": 2.0,
        "selected_restaurant": {"place_id": "p1", "name": "Luigi's", "latitude": 1.0, "longitude": 2.0},
    }
    result = upload_http.run(body, "user-oid-1")

    assert "error" in result


def test_returns_error_when_selected_restaurant_missing_required_field():
    body = {"selected_restaurant": {"place_id": "p1", "name": "Luigi's", "latitude": 1.0}}
    result = upload_http.run(body, "user-oid-1")

    assert "error" in result


def test_selected_restaurant_creates_job_with_selected_restaurant_id(monkeypatch):
    monkeypatch.setattr(
        upload_http.blob,
        "generate_upload_sas_url",
        lambda: {"blob_url": "https://x/blob", "sas_url": "https://x/blob?sig=abc"},
    )
    monkeypatch.setattr(upload_http.queue, "send_job_message", lambda job_id: None)

    conn = MagicMock()
    monkeypatch.setattr(upload_http.db, "get_connection", lambda: _ConnectionCtx(conn))

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

    assert "job_id" in result
    assert len(upserted) == 1
    assert upserted[0][0] == "place-1"

    insert_calls = [c for c in conn.cursor().execute.call_args_list if "INSERT INTO Jobs" in c.args[0]]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[-1] == "place-1"  # SelectedRestaurantId is the last bound param
