"""Per-user call quotas held in DynamoDB.

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

Two things improved in the move off SQL Server:

- **The increment is atomic.** `ADD call_count :one` under a condition is a single
  round trip that cannot interleave, replacing the `UPDLOCK, HOLDLOCK` range lock
  the SQL version needed to stop two concurrent requests both reading an
  under-limit count and both incrementing past it.
- **Expiry is free.** DynamoDB's TTL reaps aged-out buckets, replacing the
  housekeeping `DELETE` that ran on every call. Note TTL deletion is best-effort
  and can lag by up to ~48 hours, so the read below still bounds itself by an
  explicit key range rather than trusting the table to be clean.

One honest caveat: the *hourly* cap is enforced atomically by the condition
expression, but the *daily* cap is read-then-checked. Under exact concurrency a
user could overshoot the daily limit slightly. That is a deliberate trade - making
both atomic needs a second rolling counter, which is precisely the two-counters-
that-drift design this scheme was chosen to avoid. The hourly cap being hard means
the overshoot is bounded by one hour's allowance.
"""

import datetime

from shared import config, ddb

DAY_BUCKETS = 24

# Slack on top of the 24-hour window before a bucket becomes eligible for TTL
# deletion. Only needs to exceed the window; the read is key-bounded anyway.
_TTL_SLACK_HOURS = 2


class Action:
    """Values used in the rate-counter sort key."""

    SCAN = "scan"
    RECIPE = "recipe"


# Limits are read through the config getters rather than captured at import time so
# a changed setting takes effect on the next call, not the next cold start.
_ACTIONS = {
    Action.SCAN: (config.scan_rate_limit_per_hour, config.scan_rate_limit_per_day, "scans"),
    Action.RECIPE: (config.recipe_rate_limit_per_hour, config.recipe_rate_limit_per_day, "recipe generations"),
}

_BUCKET_FORMAT = "%Y-%m-%dT%H"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _bucket_of(moment: datetime.datetime) -> datetime.datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _bucket_key(moment: datetime.datetime) -> str:
    """Hour-resolution bucket label. ISO ordering is lexicographic ordering."""
    return moment.strftime(_BUCKET_FORMAT)


def _parse_bucket(key: str) -> datetime.datetime:
    return datetime.datetime.strptime(key, _BUCKET_FORMAT).replace(tzinfo=datetime.timezone.utc)


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


def _read_window(user_oid: str, action: str, window_start: datetime.datetime,
                 bucket: datetime.datetime) -> list[dict]:
    """Read this user's live buckets for one action.

    Bounded by an explicit sort-key range so expired-but-not-yet-reaped buckets
    cannot be counted. Both bounds share the `<action>#` prefix, so the range
    cannot bleed into the other action's counters.
    """
    return ddb.query_range(
        ddb.rate_pk(user_oid),
        ddb.rate_sk(action, _bucket_key(window_start)),
        ddb.rate_sk(action, _bucket_key(bucket)),
    )


def _consume(user_oid: str, action: str, bucket: datetime.datetime, per_hour: int) -> bool:
    """Atomically increment the current bucket unless it is already at the cap.

    Returns False if the conditional check failed, meaning another concurrent
    request took the last unit of this hour's allowance between our read and this
    write.
    """
    expires_at = int((bucket + datetime.timedelta(hours=DAY_BUCKETS + _TTL_SLACK_HOURS)).timestamp())
    table = ddb.get_table()
    try:
        table.update_item(
            Key={"PK": ddb.rate_pk(user_oid), "SK": ddb.rate_sk(action, _bucket_key(bucket))},
            UpdateExpression="ADD call_count :one SET expires_at = :ttl, user_id = :uid, #a = :action",
            ConditionExpression="attribute_not_exists(call_count) OR call_count < :cap",
            ExpressionAttributeNames={"#a": "action"},
            ExpressionAttributeValues={
                ":one": 1,
                ":cap": per_hour,
                ":ttl": expires_at,
                ":uid": user_oid,
                ":action": action,
            },
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True


def check_and_consume(user_oid: str, action: str) -> dict:
    """Consume one unit of this user's quota for `action`.

    Returns `{"allowed": True, ...}`, or `{"allowed": False, "error": ...,
    "retry_after_seconds": ...}` for the caller to turn into a 429.

    A denied call consumes nothing. Incrementing on rejection would let a client
    that retries into a closed window push its own reset further and further out,
    turning a one-hour cap into an indefinite lockout.
    """
    if not config.rate_limit_enabled():
        return {"allowed": True}

    per_hour_getter, per_day_getter, noun = _ACTIONS[action]
    per_hour, per_day = per_hour_getter(), per_day_getter()

    now = _now()
    bucket = _bucket_of(now)
    window_start = bucket - datetime.timedelta(hours=DAY_BUCKETS - 1)

    rows = _read_window(user_oid, action, window_start, bucket)

    bucket_key = _bucket_key(bucket)
    hour_count = sum(row.get("call_count", 0) for row in rows if row["SK"].endswith(f"#{bucket_key}"))
    day_count = sum(row.get("call_count", 0) for row in rows)

    if hour_count >= per_hour:
        resets_at = bucket + datetime.timedelta(hours=1)
        return _denied(per_hour, noun, "hour", _seconds_until(resets_at, now))

    if day_count >= per_day:
        # The window slides, so capacity returns when the oldest bucket ages out
        # rather than at a fixed daily reset.
        oldest = min(_parse_bucket(row["SK"].split("#", 1)[1]) for row in rows)
        resets_at = oldest + datetime.timedelta(hours=DAY_BUCKETS)
        return _denied(per_day, noun, "day", _seconds_until(resets_at, now))

    if not _consume(user_oid, action, bucket, per_hour):
        # Lost the race for this hour's last unit. Report it as an hourly denial,
        # which is exactly what it is.
        resets_at = bucket + datetime.timedelta(hours=1)
        return _denied(per_hour, noun, "hour", _seconds_until(resets_at, now))

    return {
        "allowed": True,
        "remaining_this_hour": per_hour - hour_count - 1,
        "remaining_today": per_day - day_count - 1,
    }
