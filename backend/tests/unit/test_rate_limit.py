import datetime

from shared import rate_limit


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows=()):
        self._cursor = _FakeCursor(list(rows))

    def cursor(self):
        return self._cursor

    @property
    def statements(self):
        return [sql for sql, _ in self._cursor.executed]


class _CounterRow:
    def __init__(self, window_start, call_count):
        self.WindowStart = window_start
        self.CallCount = call_count


def _bucket(hours_ago=0):
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=hours_ago)


def _merges(conn):
    return [sql for sql in conn.statements if sql.startswith("MERGE RateLimitCounters")]


def test_first_call_is_allowed_and_increments_the_current_bucket():
    conn = _FakeConn()

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert result["allowed"] is True
    assert len(_merges(conn)) == 1
    merge_sql, merge_params = conn._cursor.executed[-1]
    assert merge_params == ("user-1", rate_limit.Action.SCAN, _bucket())


def test_reports_remaining_headroom(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "30")
    conn = _FakeConn([_CounterRow(_bucket(), 4), _CounterRow(_bucket(5), 6)])

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert result["remaining_this_hour"] == 5  # 10 - 4 already used - this one
    assert result["remaining_today"] == 19  # 30 - 10 already used - this one


def test_blocks_once_the_hourly_limit_is_reached(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "3")
    conn = _FakeConn([_CounterRow(_bucket(), 3)])

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert result["allowed"] is False
    assert "3 scans" in result["error"]
    assert "per hour" in result["error"]


def test_a_blocked_call_consumes_nothing(monkeypatch):
    """Otherwise a client retrying into a closed window pushes its own reset out
    indefinitely, turning an hourly cap into a permanent lockout."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    conn = _FakeConn([_CounterRow(_bucket(), 1)])

    rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert _merges(conn) == []


def test_blocks_on_the_daily_total_even_when_this_hour_is_empty(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "12")
    conn = _FakeConn([_CounterRow(_bucket(n), 4) for n in (3, 7, 11)])

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert result["allowed"] is False
    assert "12 scans" in result["error"]
    assert "per day" in result["error"]


def test_hourly_retry_after_points_at_the_top_of_the_next_hour(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    conn = _FakeConn([_CounterRow(_bucket(), 1)])

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert 0 < result["retry_after_seconds"] <= 3600


def test_daily_retry_after_waits_for_the_oldest_bucket_to_age_out(monkeypatch):
    """The daily window slides, so capacity returns when the oldest bucket falls
    off - not at a fixed midnight reset."""
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "10")
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_DAY", "2")
    conn = _FakeConn([_CounterRow(_bucket(20), 1), _CounterRow(_bucket(2), 1)])

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert result["allowed"] is False
    # Oldest bucket is 20 hours old, so ~4 hours of the 24-hour window remain.
    assert 3 * 3600 < result["retry_after_seconds"] <= 4 * 3600


def test_scan_and_recipe_quotas_are_independent(monkeypatch):
    monkeypatch.setenv("SCAN_RATE_LIMIT_PER_HOUR", "1")
    monkeypatch.setenv("RECIPE_RATE_LIMIT_PER_HOUR", "5")
    conn = _FakeConn([_CounterRow(_bucket(), 1)])

    # Same stored count, different action - the recipe quota is nowhere near spent.
    assert rate_limit.check_and_consume("u", rate_limit.Action.SCAN, conn)["allowed"] is False
    assert rate_limit.check_and_consume("u", rate_limit.Action.RECIPE, conn)["allowed"] is True

    # Every statement filters on the action, so the two never read each other's rows.
    for sql, params in conn._cursor.executed:
        if "RateLimitCounters" in sql:
            assert rate_limit.Action.SCAN in params or rate_limit.Action.RECIPE in params


def test_expired_buckets_are_deleted_before_the_count_is_read():
    conn = _FakeConn()

    rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    statements = conn.statements
    assert statements[0].startswith("DELETE FROM RateLimitCounters")
    assert statements[1].startswith("SELECT WindowStart")


def test_the_count_is_read_under_a_range_lock():
    """Two concurrent requests from one user must not both read an under-limit
    count and then both increment past it."""
    conn = _FakeConn()

    rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    select_sql = next(sql for sql in conn.statements if sql.startswith("SELECT WindowStart"))
    assert "WITH (UPDLOCK, HOLDLOCK)" in select_sql


def test_disabled_limiter_does_not_touch_the_database(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    conn = _FakeConn([_CounterRow(_bucket(), 9999)])

    result = rate_limit.check_and_consume("user-1", rate_limit.Action.SCAN, conn)

    assert result == {"allowed": True}
    assert conn.statements == []
