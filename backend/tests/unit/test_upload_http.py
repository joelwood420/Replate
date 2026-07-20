from unittest.mock import MagicMock

import azure.functions as func

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


def test_uses_stub_oid_header_and_falls_back_to_default():
    req_with_header = func.HttpRequest(
        method="POST", url="/api/jobs", body=b"{}", headers={"X-Debug-User-Oid": "explicit-oid"}
    )
    assert upload_http.get_user_oid(req_with_header) == "explicit-oid"

    req_without_header = func.HttpRequest(method="POST", url="/api/jobs", body=b"{}", headers={})
    assert upload_http.get_user_oid(req_without_header) == upload_http.config.stub_default_user_oid()
