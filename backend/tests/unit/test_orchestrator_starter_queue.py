import asyncio
import json
from unittest.mock import MagicMock

import pytest

from shared import repository
from shared.models import JobStatus
from triggers import orchestrator_starter_queue as starter


def _create_job(**overrides):
    kwargs = {
        "job_id": "job-1",
        "user_oid": "user-1",
        "status": JobStatus.QUEUED,
        "image_key": "https://x/blob",
        "latitude": 40.7,
        "longitude": -74.0,
    }
    kwargs.update(overrides)
    return repository.create_job(**kwargs)


def test_build_orchestration_input_marks_processing_and_returns_job_data(ddb_table):
    _create_job()

    result = starter.build_orchestration_input("job-1")

    assert result == {"job_id": "job-1", "image_blob_url": "https://x/blob", "latitude": 40.7, "longitude": -74.0}
    assert repository.get_job("job-1")["status"] == JobStatus.PROCESSING


def test_build_orchestration_input_includes_selected_restaurant_id_when_set(ddb_table):
    _create_job(selected_restaurant_id="place-1")

    result = starter.build_orchestration_input("job-1")

    assert result == {
        "job_id": "job-1",
        "image_blob_url": "https://x/blob",
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


def test_handle_queue_message_decodes_message_and_starts_orchestration(monkeypatch):
    monkeypatch.setattr(
        starter,
        "build_orchestration_input",
        lambda job_id: {"job_id": job_id, "image_blob_url": "u", "latitude": 1.0, "longitude": 2.0},
    )

    message_body = json.dumps({"job_id": "job-1"}).encode("utf-8")
    client = MagicMock()
    started = {}

    async def fake_start_new(name, instance_id=None, client_input=None):
        started["name"] = name
        started["instance_id"] = instance_id
        started["client_input"] = client_input
        return "instance-1"

    client.start_new = fake_start_new

    asyncio.run(starter.handle_queue_message(message_body, client))

    assert started["name"] == "dish_orchestrator_trigger"
    assert started["instance_id"] == "job-1"
    assert started["client_input"] == {"job_id": "job-1", "image_blob_url": "u", "latitude": 1.0, "longitude": 2.0}
