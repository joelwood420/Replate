"""Exercises shared/rate_limit.py against a real SQL Server.

The unit tests use a fake cursor, so they cannot catch a T-SQL syntax error, a
column-name typo, or a locking hint the engine rejects. The MERGE and the
`WITH (UPDLOCK, HOLDLOCK)` hint in particular only ever get parsed here.
"""

import uuid

import pytest

from shared import rate_limit

pytestmark = pytest.mark.integration


@pytest.fixture
def quota_user(sql_connection):
    """A real Users row - RateLimitCounters.UserId is a foreign key to it."""
    user_id = str(uuid.uuid4())
    cursor = sql_connection.cursor()
    cursor.execute("INSERT INTO Users (UserId, Email) VALUES (?, ?)", user_id, "quota@example.com")
    sql_connection.commit()

    yield user_id

    cursor.execute("DELETE FROM RateLimitCounters WHERE UserId = ?", user_id)
    cursor.execute("DELETE FROM Users WHERE UserId = ?", user_id)
    sql_connection.commit()


def _stored_count(conn, user_id, action):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ISNULL(SUM(CallCount), 0) FROM RateLimitCounters WHERE UserId = ? AND Action = ?",
        user_id,
        action,
    )
    return cursor.fetchone()[0]


def test_counter_round_trip(sql_connection, quota_user, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "3")

    for expected in (1, 2, 3):
        assert rate_limit.check_and_consume(quota_user, rate_limit.Action.SCAN, sql_connection)["allowed"]
        sql_connection.commit()
        assert _stored_count(sql_connection, quota_user, rate_limit.Action.SCAN) == expected


def test_blocks_after_the_limit_and_stops_counting(sql_connection, quota_user, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "2")

    rate_limit.check_and_consume(quota_user, rate_limit.Action.SCAN, sql_connection)
    rate_limit.check_and_consume(quota_user, rate_limit.Action.SCAN, sql_connection)
    sql_connection.commit()

    denied = rate_limit.check_and_consume(quota_user, rate_limit.Action.SCAN, sql_connection)
    sql_connection.commit()

    assert denied["allowed"] is False
    assert denied["retry_after_seconds"] > 0
    # The rejected call must not have incremented anything.
    assert _stored_count(sql_connection, quota_user, rate_limit.Action.SCAN) == 2


def test_actions_do_not_share_a_counter(sql_connection, quota_user, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("RECIPE_RATE_LIMIT_PER_HOUR", "1")

    assert rate_limit.check_and_consume(quota_user, rate_limit.Action.SCAN, sql_connection)["allowed"]
    # Scan quota is now spent, but generation is untouched.
    assert rate_limit.check_and_consume(quota_user, rate_limit.Action.RECIPE, sql_connection)["allowed"]
    sql_connection.commit()

    assert _stored_count(sql_connection, quota_user, rate_limit.Action.SCAN) == 1
    assert _stored_count(sql_connection, quota_user, rate_limit.Action.RECIPE) == 1
