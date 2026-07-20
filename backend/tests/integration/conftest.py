import uuid

import pytest

from shared import blob, db


@pytest.fixture
def sql_connection():
    ctx = db.get_connection()
    try:
        conn = ctx.__enter__()
    except Exception as exc:
        pytest.skip(f"SQL Server not reachable: {exc}")
    yield conn
    ctx.__exit__(None, None, None)


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
