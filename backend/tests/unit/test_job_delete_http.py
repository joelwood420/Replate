from shared import repository
from shared.models import JobStatus
from triggers import job_delete_http


def test_deletes_the_job_and_its_listing(ddb_table):
    repository.create_job(
        job_id="job-1", user_oid="owner-oid", status=JobStatus.FAILED, image_key="a.jpg"
    )

    outcome = job_delete_http.run("job-1", "owner-oid")

    assert outcome["status_code"] == 200
    assert outcome["body"] == {"job_id": "job-1", "deleted": True}
    assert repository.get_job("job-1") is None
    assert repository.list_jobs("owner-oid") == []


def test_deletes_result_and_elements_too(ddb_table):
    repository.create_job(
        job_id="job-1", user_oid="owner-oid", status=JobStatus.IDENTIFIED, image_key="a.jpg"
    )
    repository.put_job_result("job-1", {"dish_name": "Cacio e Pepe"})
    repository.replace_dish_elements(
        "job-1", [{"sort_order": 0, "name": "Pasta", "role": "base", "ingredients": [], "steps": []}]
    )

    job_delete_http.run("job-1", "owner-oid")

    assert repository.get_job_result("job-1") is None
    assert repository.get_dish_elements("job-1") == []


def test_missing_job_is_404(ddb_table):
    assert job_delete_http.run("nope", "owner-oid")["status_code"] == 404


def test_another_users_job_is_403_and_left_intact(ddb_table):
    repository.create_job(
        job_id="theirs", user_oid="other-oid", status=JobStatus.COMPLETED, image_key="a.jpg"
    )

    outcome = job_delete_http.run("theirs", "owner-oid")

    assert outcome["status_code"] == 403
    assert repository.get_job("theirs") is not None


def test_in_flight_job_cannot_be_deleted(ddb_table):
    repository.create_job(
        job_id="running", user_oid="owner-oid", status=JobStatus.PROCESSING, image_key="a.jpg"
    )

    outcome = job_delete_http.run("running", "owner-oid")

    assert outcome["status_code"] == 409
    assert repository.get_job("running") is not None
