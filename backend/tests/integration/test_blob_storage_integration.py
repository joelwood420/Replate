import urllib.request
import uuid

import pytest
from azure.storage.queue import QueueClient

from shared import blob, config

pytestmark = pytest.mark.integration


def test_upload_and_download_blob_round_trip(blob_service_client, unique_container_name):
    container = blob_service_client.get_container_client(unique_container_name)
    container.create_container()
    try:
        blob_client = container.get_blob_client("test.txt")
        blob_client.upload_blob(b"hello from integration test", overwrite=True)

        downloaded = blob_client.download_blob().readall()

        assert downloaded == b"hello from integration test"
    finally:
        container.delete_container()


def test_generated_sas_url_permits_anonymous_put(blob_service_client):
    blob_name = f"{uuid.uuid4()}.jpg"
    upload_info = blob.generate_upload_sas_url(blob_name=blob_name)

    request = urllib.request.Request(
        upload_info["sas_url"],
        data=b"fake image bytes",
        method="PUT",
        headers={"x-ms-blob-type": "BlockBlob"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        status = response.status

    assert status == 201

    container = blob_service_client.get_container_client(config.blob_container_uploads())
    container.get_blob_client(blob_name).delete_blob()


def test_queue_send_and_receive_round_trip(queue_client):
    test_queue = QueueClient.from_connection_string(
        config.azure_storage_connection_string(), f"test-{uuid.uuid4().hex[:12]}"
    )
    test_queue.create_queue()
    try:
        test_queue.send_message("integration test job message")

        messages = list(test_queue.receive_messages(max_messages=1))

        assert len(messages) == 1
        assert messages[0].content == "integration test job message"

        test_queue.delete_message(messages[0])
    finally:
        test_queue.delete_queue()
