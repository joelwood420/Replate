"""Quota logic, against an in-process DynamoDB (moto).

The SQL-era version of these tests drove a fake cursor and asserted on the SQL
text that reached it, which meant they described the query rather than the
behaviour. These assert on stored counts and returned decisions instead, so they
would catch a broken key range or a malformed update expression.
"""

import datetime

import pytest

from shared import ddb, rate_limit

USER = "user-1"


def _bucket(hours_ago=0):
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=hours_ago)


def _seed(user, action, hours_ago, count):
    """Write a counter bucket directly, bypassing check_and_consume."""
    bucket = _bucket(hours_ago)
    ddb.put(
        {
            "PK": ddb.rate_pk(user),
            "SK": ddb.rate_sk(action, bucket.strftime("%Y-%m-%dT%H")),
            "call_count": count,
            "expires_at": int((bucket + datetime.timedelta(hours=26)).timestamp()),
        }
    )


def _stored(user, action):
    rows = ddb.query_prefix(ddb.rate_pk(user), f"{action}#")
    return sum(row.get("call_count", 0) for row in rows)


def test_first_call_is_allowed_and_increments_the_current_bucket(ddb_table):
    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert result["allowed"] is True
    assert _stored(USER, rate_limit.Action.SCAN) == 1


def test_reports_remaining_headroom(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "30")
    _seed(USER, rate_limit.Action.SCAN, 0, 4)
    _seed(USER, rate_limit.Action.SCAN, 5, 6)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    # 4 used this hour, 10 across the day, and this call consumes one of each.
    assert result["remaining_this_hour"] == 5
    assert result["remaining_today"] == 19


def test_blocks_once_the_hourly_limit_is_reached(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "3")
    _seed(USER, rate_limit.Action.SCAN, 0, 3)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert result["allowed"] is False
    assert "3 scans" in result["error"]
    assert "per hour" in result["error"]


def test_a_blocked_call_consumes_nothing(ddb_table, monkeypatch):
    """Otherwise a client retrying into a closed window pushes its own reset out."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "2")
    _seed(USER, rate_limit.Action.SCAN, 0, 2)

    rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert _stored(USER, rate_limit.Action.SCAN) == 2


def test_blocks_on_the_daily_total_even_when_this_hour_is_empty(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "12")
    for hours_ago in (1, 2, 3):
        _seed(USER, rate_limit.Action.SCAN, hours_ago, 4)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert result["allowed"] is False
    assert "12 scans" in result["error"]
    assert "per day" in result["error"]


def test_hourly_retry_after_points_at_the_top_of_the_next_hour(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    _seed(USER, rate_limit.Action.SCAN, 0, 1)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert 0 < result["retry_after_seconds"] <= 3600


def test_daily_retry_after_waits_for_the_oldest_bucket_to_age_out(ddb_table, monkeypatch):
    """The daily window slides, so capacity returns bucket by bucket."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "4")
    _seed(USER, rate_limit.Action.SCAN, 20, 4)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert result["allowed"] is False
    # Oldest bucket is 20 hours old, so it ages out of the 24-hour window in ~4h.
    assert 3 * 3600 < result["retry_after_seconds"] <= 5 * 3600


def test_scan_and_recipe_quotas_are_independent(ddb_table, monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("RECIPE_RATE_LIMIT_PER_HOUR", "1")
    _seed(USER, rate_limit.Action.SCAN, 0, 1)

    denied = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)
    allowed = rate_limit.check_and_consume(USER, rate_limit.Action.RECIPE)

    # The sort-key range is prefixed per action, so one cannot read the other's
    # buckets - the two quotas exist precisely because scanning and generating
    # have different cost profiles.
    assert denied["allowed"] is False
    assert allowed["allowed"] is True


def test_buckets_outside_the_daily_window_are_not_counted(ddb_table, monkeypatch):
    """TTL deletion lags by up to ~48h, so the read must bound itself by key range."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "5")
    _seed(USER, rate_limit.Action.SCAN, 30, 99)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert result["allowed"] is True
    assert result["remaining_today"] == 4


def test_a_ttl_is_always_written(ddb_table):
    rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    rows = ddb.query_prefix(ddb.rate_pk(USER), f"{rate_limit.Action.SCAN}#")

    assert rows[0]["expires_at"] > datetime.datetime.now(datetime.timezone.utc).timestamp()


def test_the_conditional_write_enforces_the_cap_on_its_own(ddb_table, monkeypatch):
    """The read-and-check is an optimisation; the ConditionExpression is the guard.

    Calling _consume directly skips the read, leaving only the conditional write -
    which is what stops two concurrent requests both taking the last unit.
    """
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    _seed(USER, rate_limit.Action.SCAN, 0, 1)

    assert rate_limit._consume(USER, rate_limit.Action.SCAN, _bucket(), 1) is False
    assert _stored(USER, rate_limit.Action.SCAN) == 1


def test_disabled_limiter_does_not_touch_the_table(ddb_table, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    _seed(USER, rate_limit.Action.SCAN, 0, 99)

    result = rate_limit.check_and_consume(USER, rate_limit.Action.SCAN)

    assert result["allowed"] is True
    assert _stored(USER, rate_limit.Action.SCAN) == 99


@pytest.mark.parametrize(
    "seconds,expected",
    [(30, "less than a minute"), (90, "2 minutes"), (60, "1 minute"), (7200, "2 hours")],
)
def test_humanized_retry_windows(seconds, expected):
    assert rate_limit._humanize(seconds) == expected
