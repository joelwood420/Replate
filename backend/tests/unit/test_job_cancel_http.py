import pytest

from shared import repository
from shared.models import JobStatus
from triggers import job_cancel_http


@pytest.fixture
def stopped(monkeypatch):
    """Capture stop_execution calls instead of hitting Step Functions."""
    calls = []

    def fake_stop(arn, name):
        calls.append({"arn": arn, "name": name})
        return True

    monkeypatch.setattr(job_cancel_http.sfn, "stop_execution", fake_stop)
    monkeypatch.setenv("IDENTIFY_STATE_MACHINE_ARN", "arn:aws:states:::stateMachine:identify")
    return calls


def _job(status=JobStatus.PROCESSING, owner="owner-oid"):
    return repository.create_job(
        job_id="job-1", user_oid=owner, status=status, image_key="uploads/p.jpg"
    )


def test_returns_404_for_unknown_job(ddb_table, stopped):
    assert job_cancel_http.run("missing", "owner-oid")["status_code"] == 404
    assert stopped == []


def test_returns_403_for_a_non_owner(ddb_table, stopped):
    _job()
    assert job_cancel_http.run("job-1", "someone-else")["status_code"] == 403
    assert stopped == []


@pytest.mark.parametrize("status", [JobStatus.IDENTIFIED, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED])
def test_returns_409_when_nothing_is_in_flight(ddb_table, stopped, status):
    _job(status=status)

    result = job_cancel_http.run("job-1", "owner-oid")

    assert result["status_code"] == 409
    assert stopped == []
    # A non-cancellable job is left exactly as it was.
    assert repository.get_job("job-1")["status"] == status


def test_cancels_a_processing_job(ddb_table, stopped):
    _job(status=JobStatus.PROCESSING)

    result = job_cancel_http.run("job-1", "owner-oid")

    assert result == {"status_code": 200, "body": {"job_id": "job-1", "status": JobStatus.CANCELLED}}
    assert repository.get_job("job-1")["status"] == JobStatus.CANCELLED
    # The identify execution, named after the job, is the one stopped.
    assert stopped[0]["arn"] == "arn:aws:states:::stateMachine:identify"
    assert stopped[0]["name"] == job_cancel_http.sfn.sanitize_name("job-1")


def test_cancels_a_queued_job(ddb_table, stopped):
    _job(status=JobStatus.QUEUED)

    result = job_cancel_http.run("job-1", "owner-oid")

    assert result["status_code"] == 200
    assert repository.get_job("job-1")["status"] == JobStatus.CANCELLED


def test_cancelled_status_reaches_the_cookbook_listing(ddb_table, stopped):
    """Status is a projected field - the listing must reflect the cancel too."""
    _job(status=JobStatus.PROCESSING)

    job_cancel_http.run("job-1", "owner-oid")

    assert repository.list_jobs("owner-oid")[0]["status"] == JobStatus.CANCELLED
