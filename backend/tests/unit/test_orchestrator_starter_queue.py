import json

import pytest

from shared import repository
from shared.models import JobStatus
from triggers import orchestrator_starter_queue as starter


def _create_job(**overrides):
    kwargs = {
        "job_id": "job-1",
        "user_oid": "user-1",
        "status": JobStatus.QUEUED,
        "image_key": "uploads/photo.jpg",
        "latitude": 40.7,
        "longitude": -74.0,
    }
    kwargs.update(overrides)
    return repository.create_job(**kwargs)


def test_build_orchestration_input_marks_processing_and_returns_job_data(ddb_table):
    _create_job()

    result = starter.build_orchestration_input("job-1")

    assert result == {"job_id": "job-1", "image_key": "uploads/photo.jpg", "latitude": 40.7, "longitude": -74.0}
    assert repository.get_job("job-1")["status"] == JobStatus.PROCESSING


def test_build_orchestration_input_includes_selected_restaurant_id_when_set(ddb_table):
    _create_job(selected_restaurant_id="place-1")

    result = starter.build_orchestration_input("job-1")

    assert result == {
        "job_id": "job-1",
        "image_key": "uploads/photo.jpg",
        "latitude": 40.7,
        "longitude": -74.0,
        "selected_restaurant_id": "place-1",
    }


def test_build_orchestration_input_raises_for_unknown_job(ddb_table):
    with pytest.raises(ValueError, match="job-missing"):
        starter.build_orchestration_input("job-missing")


def test_processing_status_reaches_the_cookbook_listing(ddb_table):
    """Status is a projected field - the listing must not go stale."""
    _create_job()

    starter.build_orchestration_input("job-1")

    assert repository.list_jobs("user-1")[0]["status"] == JobStatus.PROCESSING


@pytest.fixture
def started(monkeypatch):
    """Capture StartExecution calls instead of making them."""
    calls = []

    def fake_start(arn, name, payload):
        calls.append({"arn": arn, "name": name, "payload": payload})
        return True

    monkeypatch.setattr(starter.sfn, "start_execution", fake_start)
    monkeypatch.setenv("IDENTIFY_STATE_MACHINE_ARN", "arn:aws:states:::stateMachine:identify")
    return calls


def _sqs_event(*job_ids):
    return {
        "Records": [
            {"messageId": f"msg-{index}", "body": json.dumps({"job_id": job_id})}
            for index, job_id in enumerate(job_ids)
        ]
    }


def test_handler_decodes_the_message_and_starts_the_state_machine(ddb_table, started):
    _create_job()

    result = starter.handler(_sqs_event("job-1"))

    assert result == {"batchItemFailures": []}
    assert started[0]["arn"] == "arn:aws:states:::stateMachine:identify"
    assert started[0]["name"] == "job-1"
    assert started[0]["payload"] == {
        "job_id": "job-1",
        "image_key": "uploads/photo.jpg",
        "latitude": 40.7,
        "longitude": -74.0,
    }


def test_the_execution_is_named_after_the_job(ddb_table, started):
    """Step Functions refuses a duplicate execution name, which is what makes a
    redelivered SQS message harmless - the same role Durable's instance_id played."""
    _create_job()

    starter.handler(_sqs_event("job-1"))

    assert started[0]["name"] == starter.sfn.sanitize_name("job-1")


def test_one_bad_message_does_not_fail_the_whole_batch(ddb_table, started):
    """A raised error would make SQS redeliver every message in the batch, re-running
    work that already succeeded."""
    _create_job()

    result = starter.handler(_sqs_event("job-1", "job-does-not-exist"))

    assert len(started) == 1
    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-1"}]}


def test_a_malformed_message_body_is_reported_not_raised(ddb_table, started):
    result = starter.handler({"Records": [{"messageId": "msg-0", "body": "not json"}]})

    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-0"}]}
