"""Exercises shared/rate_limit.py against a real DynamoDB endpoint.

The unit tests stub the table, so they cannot catch a malformed UpdateExpression,
a reserved-word collision, or a key range that silently matches nothing. The
conditional `ADD` and the two-bound sort-key query only ever get parsed here.
"""

import pytest

from shared import ddb, rate_limit

pytestmark = pytest.mark.integration


def _stored_count(user_oid, action):
    rows = ddb.query_prefix(ddb.rate_pk(user_oid), f"{action}#")
    return sum(row.get("call_count", 0) for row in rows)


def test_counter_round_trip(ddb_table, unique_user_oid, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "3")

    for expected in (1, 2, 3):
        assert rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)["allowed"]
        assert _stored_count(unique_user_oid, rate_limit.Action.SCAN) == expected


def test_blocks_after_the_limit_and_stops_counting(ddb_table, unique_user_oid, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "2")

    rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)
    rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)

    denied = rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)

    assert denied["allowed"] is False
    assert denied["retry_after_seconds"] > 0
    # The rejected call must not have incremented anything - otherwise a client
    # that retries into a closed window pushes its own reset out indefinitely.
    assert _stored_count(unique_user_oid, rate_limit.Action.SCAN) == 2


def test_actions_do_not_share_a_counter(ddb_table, unique_user_oid, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("RECIPE_RATE_LIMIT_PER_HOUR", "1")

    assert rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)["allowed"]
    # Scan quota is now spent, but generation is untouched. The sort-key range is
    # prefixed per action, so the two cannot read each other's buckets.
    assert rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.RECIPE)["allowed"]

    assert _stored_count(unique_user_oid, rate_limit.Action.SCAN) == 1
    assert _stored_count(unique_user_oid, rate_limit.Action.RECIPE) == 1


def test_conditional_increment_holds_the_hourly_cap(ddb_table, unique_user_oid, monkeypatch):
    """The ConditionExpression, not the read, is what actually enforces the cap.

    Consuming the allowance and then calling `_consume` directly bypasses the
    read-and-check, leaving only the conditional write - which must refuse.
    """
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)

    bucket = rate_limit._bucket_of(rate_limit._now())
    assert rate_limit._consume(unique_user_oid, rate_limit.Action.SCAN, bucket, 1) is False
    assert _stored_count(unique_user_oid, rate_limit.Action.SCAN) == 1


def test_ttl_attribute_is_written(ddb_table, unique_user_oid):
    """Buckets self-expire; without expires_at the table would grow forever."""
    rate_limit.check_and_consume(unique_user_oid, rate_limit.Action.SCAN)

    rows = ddb.query_prefix(ddb.rate_pk(unique_user_oid), f"{rate_limit.Action.SCAN}#")

    assert rows and rows[0]["expires_at"] > 0
