import pytest

from shared import repository
from shared.models import JobStatus
from triggers import job_uploaded_http

_OWNER = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(job_uploaded_http.queue, "send_job_message", messages.append)
    return messages


def _job(status=JobStatus.QUEUED, owner=_OWNER):
    return repository.create_job(
        job_id="job-1", user_oid=owner, status=status, image_key="uploads/p.jpg"
    )


def test_queues_the_job_once_the_photo_is_there(ddb_table, sent):
    _job()

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome == {"status_code": 202, "body": {"job_id": "job-1", "status": JobStatus.QUEUED}}
    assert sent == ["job-1"]


def test_returns_404_for_unknown_job(ddb_table, sent):
    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome["status_code"] == 404
    assert sent == []


def test_returns_403_when_caller_does_not_own_the_job(ddb_table, sent):
    _job(owner="22222222-2222-2222-2222-222222222222")

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome["status_code"] == 403
    assert sent == []


def test_a_repeated_call_does_not_start_the_pipeline_twice(ddb_table, sent):
    """A retried request must not enqueue a second time - only a job still waiting
    on its photo can be started."""
    _job(status=JobStatus.PROCESSING)

    outcome = job_uploaded_http.run("job-1", _OWNER)

    assert outcome["status_code"] == 409
    assert sent == []


def test_does_not_requeue_a_finished_job(ddb_table, sent):
    _job(status=JobStatus.COMPLETED)

    assert job_uploaded_http.run("job-1", _OWNER)["status_code"] == 409
    assert sent == []
