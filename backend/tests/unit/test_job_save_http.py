from shared import repository
from shared.models import JobStatus
from triggers import job_save_http


def _job(owner="owner-oid"):
    return repository.create_job(
        job_id="job-1", user_oid=owner, status=JobStatus.IDENTIFIED, image_key="uploads/p.jpg"
    )


def test_returns_404_for_unknown_job_id(ddb_table):
    result = job_save_http.run("missing-job", "owner-oid", True)

    assert result["status_code"] == 404


def test_returns_403_when_oid_does_not_match_job_owner(ddb_table):
    _job()

    result = job_save_http.run("job-1", "different-oid", True)

    assert result["status_code"] == 403


def test_saves_job_and_returns_is_saved_true(ddb_table):
    _job()

    result = job_save_http.run("job-1", "owner-oid", True)

    assert result == {"status_code": 200, "body": {"job_id": "job-1", "is_saved": True}}
    assert repository.get_job("job-1")["is_saved"] is True


def test_unsaves_job_and_returns_is_saved_false(ddb_table):
    _job()
    repository.update_job("job-1", is_saved=True)

    result = job_save_http.run("job-1", "owner-oid", False)

    assert result == {"status_code": 200, "body": {"job_id": "job-1", "is_saved": False}}
    assert repository.get_job("job-1")["is_saved"] is False


def test_the_change_reaches_the_cookbook_listing(ddb_table):
    """is_saved is a projected field, and the Cookbook screen filters on it -
    if only the canonical item were updated the filter would disagree."""
    _job()

    job_save_http.run("job-1", "owner-oid", True)

    assert [j["job_id"] for j in repository.list_jobs("owner-oid", saved=True)] == ["job-1"]


def test_a_rejected_request_changes_nothing(ddb_table):
    _job()

    job_save_http.run("job-1", "different-oid", True)

    assert repository.get_job("job-1")["is_saved"] is False
