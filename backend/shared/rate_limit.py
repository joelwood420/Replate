"""Per-user call quotas held in Azure SQL (CLAUDE.md Phase 3 step 5).

The pipeline runs as two separately-triggered stages with very different cost and
frequency profiles, so they get separate quotas rather than one shared counter.
Scanning a photo is automatic and happens whenever the user points the camera at a
plate; reverse-engineering is a deliberate button press in the cookbook and is the
heaviest AI call in the app. One combined limit would either be too tight to scan
freely or too loose to cap generation spend.

Counters are bucketed by hour. The hourly limit reads the current bucket and the
daily limit sums the last 24, so both windows come from one bucket granularity -
there is no second counter that can drift out of step with the first. The daily
window therefore slides at hour resolution rather than resetting at midnight, which
also means no midnight stampede.
"""

import datetime

from shared import config

DAY_BUCKETS = 24


class Action:
    """Values stored in RateLimitCounters.Action - NVARCHAR(30)."""

    SCAN = "scan"
    RECIPE = "recipe"


# Limits are read through the config getters rather than captured at import time so
# a changed app setting takes effect on the next call, not the next cold start.
_ACTIONS = {
    Action.SCAN: (config.scan_rate_limit_per_hour, config.scan_rate_limit_per_day, "scans"),
    Action.RECIPE: (config.recipe_rate_limit_per_hour, config.recipe_rate_limit_per_day, "recipe generations"),
}


def _now() -> datetime.datetime:
    # Naive UTC, matching the DATETIME2 columns everywhere else in the schema -
    # SQL Server has no timezone on DATETIME2, and SYSUTCDATETIME() writes naive UTC.
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _bucket_of(moment: datetime.datetime) -> datetime.datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _seconds_until(moment: datetime.datetime, now: datetime.datetime) -> int:
    # Floor of 1: a Retry-After of 0 reads as "retry immediately", which is the one
    # thing a throttled client must not do.
    return max(1, int((moment - now).total_seconds()))


def _humanize(seconds: int) -> str:
    if seconds < 60:
        return "less than a minute"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = round(seconds / 3600)
    return f"{hours} hour{'s' if hours != 1 else ''}"


def _denied(limit: int, noun: str, per: str, retry_after_seconds: int) -> dict:
    return {
        "allowed": False,
        "error": (
            f"You have used all {limit} {noun} allowed per {per}. "
            f"Try again in {_humanize(retry_after_seconds)}."
        ),
        "retry_after_seconds": retry_after_seconds,
    }


def check_and_consume(user_oid: str, action: str, conn) -> dict:
    """Consume one unit of this user's quota for `action`.

    Returns `{"allowed": True, ...}`, or `{"allowed": False, "error": ...,
    "retry_after_seconds": ...}` for the caller to turn into a 429.

    A denied call consumes nothing. Incrementing on rejection would let a client
    that retries into a closed window push its own reset further and further out,
    turning a one-hour cap into an indefinite lockout.

    Must be called on a connection inside an open transaction (`db.get_connection`
    provides one) - the read lock below only holds for the life of that transaction.
    """
    if not config.rate_limit_enabled():
        return {"allowed": True}

    per_hour_getter, per_day_getter, noun = _ACTIONS[action]
    per_hour, per_day = per_hour_getter(), per_day_getter()

    now = _now()
    bucket = _bucket_of(now)
    window_start = bucket - datetime.timedelta(hours=DAY_BUCKETS - 1)

    cursor = conn.cursor()

    # Housekeeping first, so the read below sees only live buckets and the table
    # stays at a bounded 24 rows per user per action.
    cursor.execute(
        "DELETE FROM RateLimitCounters WHERE UserId = ? AND Action = ? AND WindowStart < ?",
        user_oid,
        action,
        window_start,
    )

    # UPDLOCK + HOLDLOCK takes a range lock held to the end of the transaction.
    # Without it two concurrent requests from the same user can both read a count
    # that is under the limit and then both increment past it.
    cursor.execute(
        "SELECT WindowStart, CallCount FROM RateLimitCounters WITH (UPDLOCK, HOLDLOCK) "
        "WHERE UserId = ? AND Action = ? AND WindowStart >= ?",
        user_oid,
        action,
        window_start,
    )
    rows = cursor.fetchall()

    hour_count = sum(row.CallCount for row in rows if row.WindowStart == bucket)
    day_count = sum(row.CallCount for row in rows)

    if hour_count >= per_hour:
        resets_at = bucket + datetime.timedelta(hours=1)
        return _denied(per_hour, noun, "hour", _seconds_until(resets_at, now))

    if day_count >= per_day:
        # The window slides, so capacity returns when the oldest bucket ages out
        # rather than at a fixed daily reset.
        resets_at = min(row.WindowStart for row in rows) + datetime.timedelta(hours=DAY_BUCKETS)
        return _denied(per_day, noun, "day", _seconds_until(resets_at, now))

    cursor.execute(
        "MERGE RateLimitCounters AS target "
        "USING (SELECT ? AS UserId, ? AS Action, ? AS WindowStart) AS src "
        "ON target.UserId = src.UserId AND target.Action = src.Action "
        "AND target.WindowStart = src.WindowStart "
        "WHEN MATCHED THEN UPDATE SET CallCount = target.CallCount + 1 "
        "WHEN NOT MATCHED THEN INSERT (UserId, Action, WindowStart, CallCount) "
        "VALUES (src.UserId, src.Action, src.WindowStart, 1);",
        user_oid,
        action,
        bucket,
    )

    return {
        "allowed": True,
        "remaining_this_hour": per_hour - hour_count - 1,
        "remaining_today": per_day - day_count - 1,
    }
