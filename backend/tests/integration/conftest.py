import uuid

import pytest

from shared import blob, config, ddb


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
def unique_user_oid():
    """A fresh user id per test, so tests sharing one table cannot collide."""
    return str(uuid.uuid4())


@pytest.fixture
def blob_service_client():
    try:
        client = blob._service_client()
        client.get_service_properties()
    except Exception as exc:
        pytest.skip(f"Azurite blob endpoint not reachable: {exc}")
    return client


@pytest.fixture
def queue_client():
    from shared.queue import _queue_client

    try:
        client = _queue_client()
        client.get_queue_properties()
    except Exception as exc:
        pytest.skip(f"Azurite queue endpoint not reachable: {exc}")
    return client


@pytest.fixture
def unique_container_name():
    return f"test-{uuid.uuid4().hex[:12]}"
