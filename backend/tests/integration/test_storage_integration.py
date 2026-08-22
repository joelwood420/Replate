"""S3 presigned URLs and the SQS round trip, against real endpoints.

Replaces the Azurite blob/queue suite. The point of these is the same as before:
a presigned URL is only useful if an *unauthenticated* client can actually use
it, and that is precisely what a mocked S3 client cannot tell you.
"""

import httpx
import pytest

from shared import config, queue, storage

pytestmark = pytest.mark.integration


def test_presigned_put_permits_an_unauthenticated_upload(s3_bucket, unique_key):
    """The whole upload design rests on this: the browser holds no credentials."""
    upload_info = storage.generate_upload_url(key=unique_key)

    response = httpx.put(upload_info["upload_url"], content=b"fake-jpeg-bytes", timeout=15)

    assert response.status_code in (200, 204)
    assert storage.object_exists(unique_key) is True

    storage.get_client().delete_object(Bucket=s3_bucket, Key=unique_key)


def test_presigned_get_returns_the_uploaded_bytes(s3_bucket, unique_key):
    storage.get_client().put_object(Bucket=s3_bucket, Key=unique_key, Body=b"hello from a test")

    read_url = storage.generate_read_url(unique_key)
    response = httpx.get(read_url, timeout=15)

    assert response.status_code == 200
    assert response.content == b"hello from a test"

    storage.get_client().delete_object(Bucket=s3_bucket, Key=unique_key)


def test_upload_url_is_write_only(s3_bucket, unique_key):
    """A GET against a URL signed for put_object must be refused - otherwise the
    write-only guarantee the client is handed is not a guarantee at all."""
    upload_info = storage.generate_upload_url(key=unique_key)
    storage.get_client().put_object(Bucket=s3_bucket, Key=unique_key, Body=b"x")

    response = httpx.get(upload_info["upload_url"], timeout=15)

    assert response.status_code == 403

    storage.get_client().delete_object(Bucket=s3_bucket, Key=unique_key)


def test_object_exists_is_false_for_a_reserved_but_unused_key(s3_bucket):
    """generate_upload_url only reserves a name - moderation relies on this
    distinction to tell "never uploaded" from "unsafe"."""
    upload_info = storage.generate_upload_url()

    assert storage.object_exists(upload_info["key"]) is False


def test_the_bucket_is_not_publicly_readable(s3_bucket, unique_key):
    # Denying an *unsigned* (anonymous) GET is S3 Block Public Access / default-private
    # behaviour, which LocalStack Community does not emulate: it returns the bytes with 200.
    # This assertion therefore only means something against real S3, so skip it when pointed
    # at a local endpoint. The sibling test_upload_url_is_write_only still runs everywhere
    # (it needs only signature validation, which the compose file enables).
    if config.aws_endpoint_url():
        pytest.skip("anonymous-read denial is a real-S3 property LocalStack does not emulate")

    storage.get_client().put_object(Bucket=s3_bucket, Key=unique_key, Body=b"secret")

    endpoint = config.aws_endpoint_url() or f"https://{s3_bucket}.s3.amazonaws.com"
    unsigned = f"{endpoint.rstrip('/')}/{s3_bucket}/{unique_key}"
    response = httpx.get(unsigned, timeout=15)

    assert response.status_code in (401, 403, 404)

    storage.get_client().delete_object(Bucket=s3_bucket, Key=unique_key)


def test_job_message_round_trip(sqs_queue):
    queue.send_job_message("job-integration-1")

    received = queue.get_client().receive_message(
        QueueUrl=sqs_queue, MaxNumberOfMessages=1, WaitTimeSeconds=5
    )

    messages = received.get("Messages", [])
    assert messages, "no message arrived on the queue"
    # Plain JSON, not base64 - none of the messageEncoding trouble Azure Queue
    # Storage needed a host.json workaround for.
    assert queue.decode_job_message(messages[0]["Body"]) == {"job_id": "job-integration-1"}

    queue.get_client().delete_message(
        QueueUrl=sqs_queue, ReceiptHandle=messages[0]["ReceiptHandle"]
    )
