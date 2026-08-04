from unittest.mock import MagicMock

from shared.models import JobStatus
from triggers import job_uploaded_http

_OWNER = "11111111-1111-1111-1111-111111111111"


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def _patch(monkeypatch, row):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = row
    monkeypatch.setattr(job_uploaded_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    sent = []
    monkeypatch.setattr(job_uploaded_http.queue, "send_job_message", lambda job_id: sent.append(job_id))
    return sent


def _row(status=JobStatus.QUEUED, owner=_OWNER):
    return MagicMock(UserId=owner, Status=status)


def test_queues_the_job_once_the_photo_is_there(monkeypatch):
    sent = _patch(monkeypatch, _row())

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome == {"status_code": 202, "body": {"job_id": "job-1", "status": JobStatus.QUEUED}}
    assert sent == ["job-1"]


def test_returns_404_for_unknown_job(monkeypatch):
    sent = _patch(monkeypatch, None)

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome["status_code"] == 404
    assert sent == []


def test_returns_403_when_caller_does_not_own_the_job(monkeypatch):
    sent = _patch(monkeypatch, _row(owner="22222222-2222-2222-2222-222222222222"))

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome["status_code"] == 403
    assert sent == []


def test_a_repeated_call_does_not_start_the_pipeline_twice(monkeypatch):
    """A retried request must not enqueue a second time - only a job still waiting
    on its photo can be started."""
    sent = _patch(monkeypatch, _row(status=JobStatus.PROCESSING))

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome["status_code"] == 409
    assert sent == []


def test_does_not_requeue_a_finished_job(monkeypatch):
    sent = _patch(monkeypatch, _row(status=JobStatus.COMPLETED))

    assert job_uploaded_http.run("job-1", _OWNER)["status_code"] == 409
    assert sent == []
