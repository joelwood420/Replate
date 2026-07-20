import json

from azure.core.exceptions import ResourceExistsError
from azure.storage.queue import QueueClient

from shared import config


def _queue_client() -> QueueClient:
    client = QueueClient.from_connection_string(
        config.azure_storage_connection_string(), config.queue_name_jobs()
    )
    try:
        client.create_queue()
    except ResourceExistsError:
        pass
    return client


def send_job_message(job_id: str) -> None:
    _queue_client().send_message(json.dumps({"job_id": job_id}))


def decode_job_message(message_content: str) -> dict:
    return json.loads(message_content)
