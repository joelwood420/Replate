from unittest.mock import MagicMock

from triggers import job_save_http


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def test_returns_404_for_unknown_job_id(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    monkeypatch.setattr(job_save_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = job_save_http.run("missing-job", "owner-oid", True)

    assert result["status_code"] == 404


def test_returns_403_when_oid_does_not_match_job_owner(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(UserId="owner-oid")
    monkeypatch.setattr(job_save_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = job_save_http.run("job-1", "different-oid", True)

    assert result["status_code"] == 403


def test_saves_job_and_returns_is_saved_true(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(UserId="owner-oid")
    monkeypatch.setattr(job_save_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = job_save_http.run("job-1", "owner-oid", True)

    assert result == {"status_code": 200, "body": {"job_id": "job-1", "is_saved": True}}
    update_calls = [c for c in conn.cursor().execute.call_args_list if "UPDATE Jobs" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1] == 1
    assert update_calls[0].args[2] == "job-1"


def test_unsaves_job_and_returns_is_saved_false(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(UserId="owner-oid")
    monkeypatch.setattr(job_save_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = job_save_http.run("job-1", "owner-oid", False)

    assert result == {"status_code": 200, "body": {"job_id": "job-1", "is_saved": False}}
    update_calls = [c for c in conn.cursor().execute.call_args_list if "UPDATE Jobs" in c.args[0]]
    assert update_calls[0].args[1] == 0
