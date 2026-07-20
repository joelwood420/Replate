import asyncio
import json
from unittest.mock import MagicMock

from triggers import orchestrator_starter_queue as starter


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def test_build_orchestration_input_marks_processing_and_returns_job_data(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(
        ImageBlobUrl="https://x/blob", Latitude=40.7, Longitude=-74.0
    )
    monkeypatch.setattr(starter.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = starter.build_orchestration_input("job-1")

    assert result == {"job_id": "job-1", "image_blob_url": "https://x/blob", "latitude": 40.7, "longitude": -74.0}
    update_calls = [c for c in conn.cursor().execute.call_args_list if "UPDATE Jobs" in c.args[0]]
    assert len(update_calls) == 1


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
