import pytest

from shared import repository
from shared.models import JobStatus
from triggers import jobs_list_http


@pytest.fixture(autouse=True)
def stub_presigned_url(monkeypatch):
    monkeypatch.setattr(jobs_list_http.storage, "generate_read_url", lambda key: f"{key}?sig=abc")


def test_returns_empty_list_when_caller_has_no_jobs(ddb_table):
    assert jobs_list_http.run("owner-oid", None, 20) == []


def test_maps_fields_including_image_url_and_dish_name(ddb_table):
    job = repository.create_job(
        job_id="job-1",
        user_oid="owner-oid",
        status=JobStatus.COMPLETED,
        image_key="uploads/photo.jpg",
    )
    repository.update_job("job-1", dish_name="Margherita Pizza", restaurant_name="Marchetti")

    result = jobs_list_http.run("owner-oid", None, 20)

    assert result == [
        {
            "job_id": "job-1",
            "status": JobStatus.COMPLETED,
            "is_saved": False,
            "created_at": job["created_at"],
            "dish_name": "Margherita Pizza",
            "restaurant_name": "Marchetti",
            "image_url": "uploads/photo.jpg?sig=abc",
        }
    ]


def test_scopes_the_listing_to_the_caller(ddb_table):
    repository.create_job(job_id="mine", user_oid="owner-oid", status="Queued", image_key="a.jpg")
    repository.create_job(job_id="theirs", user_oid="other-oid", status="Queued", image_key="b.jpg")

    result = jobs_list_http.run("owner-oid", None, 20)

    # Partitioned by user, so another user's jobs are not merely filtered out -
    # they are never read.
    assert [job["job_id"] for job in result] == ["mine"]


def test_saved_filter_narrows_the_listing(ddb_table):
    repository.create_job(job_id="saved", user_oid="owner-oid", status="Queued", image_key="a.jpg")
    repository.create_job(job_id="unsaved", user_oid="owner-oid", status="Queued", image_key="b.jpg")
    repository.update_job("saved", is_saved=True)

    assert [j["job_id"] for j in jobs_list_http.run("owner-oid", True, 20)] == ["saved"]
    assert [j["job_id"] for j in jobs_list_http.run("owner-oid", False, 20)] == ["unsaved"]


def test_no_saved_filter_returns_everything(ddb_table):
    repository.create_job(job_id="saved", user_oid="owner-oid", status="Queued", image_key="a.jpg")
    repository.create_job(job_id="unsaved", user_oid="owner-oid", status="Queued", image_key="b.jpg")
    repository.update_job("saved", is_saved=True)

    assert len(jobs_list_http.run("owner-oid", None, 20)) == 2


def test_newest_first(ddb_table):
    for index in range(3):
        repository.create_job(
            job_id=f"job-{index}", user_oid="owner-oid", status="Queued", image_key=f"{index}.jpg"
        )

    result = jobs_list_http.run("owner-oid", None, 20)

    assert [job["job_id"] for job in result] == ["job-2", "job-1", "job-0"]


def test_limit_is_respected(ddb_table):
    for index in range(5):
        repository.create_job(
            job_id=f"job-{index}", user_oid="owner-oid", status="Queued", image_key=f"{index}.jpg"
        )

    assert len(jobs_list_http.run("owner-oid", None, 2)) == 2


def test_parse_bool_handles_true_false_and_missing():
    assert jobs_list_http._parse_bool("true") is True
    assert jobs_list_http._parse_bool("false") is False
    assert jobs_list_http._parse_bool(None) is None
