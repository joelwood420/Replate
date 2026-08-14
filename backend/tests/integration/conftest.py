import uuid

import pytest

from shared import config, ddb, queue, storage


@pytest.fixture
def ddb_table():
    """A real DynamoDB table, created if it isn't already there.

    Skips rather than fails when nothing is listening, so the marker-gated
    integration suite stays runnable on a machine with no LocalStack. Point
    AWS_ENDPOINT_URL at LocalStack (or DynamoDB Local) to exercise these.
    """
    ddb.reset_table_cache()
    try:
        from scripts.create_table import create_table

        create_table()
        table = ddb.get_table()
        table.load()
    except Exception as exc:  # noqa: BLE001 - any connection failure means "skip"
        pytest.skip(f"DynamoDB endpoint not reachable at {config.aws_endpoint_url() or 'default'}: {exc}")
    return table


@pytest.fixture
def s3_bucket():
    """The uploads bucket, created if absent. Skips when S3 is unreachable."""
    storage.reset_client_cache()
    bucket = config.s3_bucket_uploads()
    try:
        client = storage.get_client()
        existing = {entry["Name"] for entry in client.list_buckets().get("Buckets", [])}
        if bucket not in existing:
            kwargs = {"Bucket": bucket}
            region = config.aws_region()
            # us-east-1 is the one region that rejects an explicit location
            # constraint, so it has to be omitted rather than set.
            if region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            client.create_bucket(**kwargs)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"S3 endpoint not reachable at {config.aws_endpoint_url() or 'default'}: {exc}")
    return bucket


@pytest.fixture
def sqs_queue():
    """The jobs queue, created if absent. Skips when SQS is unreachable."""
    queue.reset_client_cache()
    try:
        return queue._ensure_queue()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"SQS endpoint not reachable at {config.aws_endpoint_url() or 'default'}: {exc}")


@pytest.fixture
def unique_user_oid():
    """A fresh user id per test, so tests sharing one table cannot collide."""
    return str(uuid.uuid4())


@pytest.fixture
def unique_key():
    return f"uploads/test-{uuid.uuid4().hex[:12]}.jpg"
