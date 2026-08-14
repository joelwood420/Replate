"""Low-level DynamoDB access for Replate - one table, boto3 resource API.

Replaces the Azure SQL + pyodbc layer. Every access pattern in the app is a key
lookup, so a single table with a composite key carries all of them without a GSI:

    PK                 SK                       access pattern
    USER#<oid>         PROFILE                  user by oid
    USER#<oid>         JOB#<ts>#<jobId>         jobs by user, newest first
    JOB#<jobId>        META                     job status
    JOB#<jobId>        RESULT                   match result + raw vision guess
    JOB#<jobId>        ELEMENT#<nnn>            dish element (ingredients + steps nested)
    JOB#<jobId>        CANDIDATE#<restId>       geocoded restaurant candidates
    REST#<placeId>     META                     restaurant + MenuLastFetchedAt cache gate
    REST#<placeId>     MENUITEM#<nnn>           menu items for matching
    RATE#<oid>         <action>#<bucketIso>     quota counters (TTL)
    EMBEDDINGS         TECHNIQUE#<id>           culinary technique vectors

Two notes on the sort keys. `JOB#<ts>#<jobId>` embeds a descending-friendly
timestamp so the cookbook listing falls out of the key order - that replaces the
old `ORDER BY CreatedAt DESC` and its `IX_Jobs_UserId` index. And the `#<nnn>`
suffixes are zero-padded, because DynamoDB sorts sort keys lexicographically:
`ELEMENT#10` sorts before `ELEMENT#2` without the padding.

This module deliberately holds no domain knowledge - see `shared/repository.py`
for that. It exists to own the table handle, the key format and the
float/Decimal boundary, so nothing above it has to think about boto3.
"""

import decimal
import threading

import boto3
from boto3.dynamodb.conditions import Key

from shared import config

# DynamoDB stores numbers as Decimal and boto3's resource API refuses to
# serialize float outright. Rather than sprinkle Decimal(str(x)) across the
# repository, every value crosses this module's boundary through _to_ddb /
# _from_ddb, so callers work in plain Python types throughout.
_CONTEXT = decimal.Context(prec=38)

_lock = threading.Lock()
_table = None

SORT_PAD = 4
"""Zero-padding width for numeric sort-key suffixes (ELEMENT#0007)."""


def _resource():
    kwargs = {"region_name": config.aws_region()}
    endpoint = config.aws_endpoint_url()
    if endpoint:
        # LocalStack / DynamoDB Local. Unset in a real deployment, where the
        # Lambda's execution role and the default endpoint resolution apply.
        kwargs["endpoint_url"] = endpoint
    return boto3.resource("dynamodb", **kwargs)


def get_table():
    """Return the shared Table handle, creating it on first use.

    Cached per process so a warm Lambda reuses the underlying HTTPS connection
    rather than paying TLS setup on every invocation. Guarded because Lambda can
    run handler threads concurrently within one container.
    """
    global _table
    if _table is None:
        with _lock:
            if _table is None:
                _table = _resource().Table(config.ddb_table_name())
    return _table


def client():
    """The underlying low-level DynamoDB client.

    For control-plane calls (create table, TTL) that the resource-level Table
    object doesn't expose.
    """
    return get_table().meta.client


def reset_table_cache() -> None:
    """Drop the cached handle. For tests and for endpoint changes between runs."""
    global _table
    with _lock:
        _table = None


# --------------------------------------------------------------------------
# Key construction
# --------------------------------------------------------------------------


def user_pk(user_oid: str) -> str:
    return f"USER#{user_oid}"


def job_pk(job_id: str) -> str:
    return f"JOB#{job_id}"


def restaurant_pk(restaurant_id: str) -> str:
    return f"REST#{restaurant_id}"


def rate_pk(user_oid: str) -> str:
    return f"RATE#{user_oid}"


EMBEDDINGS_PK = "EMBEDDINGS"

SK_PROFILE = "PROFILE"
SK_META = "META"
SK_RESULT = "RESULT"


def job_index_sk(created_at_iso: str, job_id: str) -> str:
    """Sort key for the user's job listing.

    ISO-8601 UTC sorts lexicographically in the same order it sorts
    chronologically, which is the whole reason the timestamp leads. The job id
    tie-breaks two jobs created in the same second.
    """
    return f"JOB#{created_at_iso}#{job_id}"


def element_sk(sort_order: int) -> str:
    return f"ELEMENT#{sort_order:0{SORT_PAD}d}"


def menu_item_sk(index: int) -> str:
    return f"MENUITEM#{index:0{SORT_PAD}d}"


def candidate_sk(restaurant_id: str) -> str:
    return f"CANDIDATE#{restaurant_id}"


def technique_sk(embedding_id: str) -> str:
    return f"TECHNIQUE#{embedding_id}"


def rate_sk(action: str, bucket_iso: str) -> str:
    return f"{action}#{bucket_iso}"


# --------------------------------------------------------------------------
# Type conversion
# --------------------------------------------------------------------------


def to_ddb(value):
    """Convert Python values into what the boto3 resource API accepts.

    float -> Decimal (DynamoDB has no float type and boto3 raises on one), and
    empty strings are preserved: DynamoDB has allowed empty string values for
    non-key attributes since 2020, so there is no need to coerce them to None
    and lose the distinction between "blank" and "absent".
    """
    if isinstance(value, float):
        return _CONTEXT.create_decimal_from_float(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, dict):
        return {k: to_ddb(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_ddb(v) for v in value]
    return value


def from_ddb(value):
    """Inverse of `to_ddb` - Decimal back to int or float.

    Integral Decimals become int so that counts, sort orders and step numbers
    round-trip as the types the rest of the code (and json.dumps) expects.
    """
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_ddb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_ddb(v) for v in value]
    return value


def strip_keys(item: dict) -> dict:
    """Drop the composite key attributes from an item before returning it.

    Callers work in domain terms; PK/SK are this layer's business.
    """
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


# --------------------------------------------------------------------------
# Thin CRUD wrappers
# --------------------------------------------------------------------------


def put(item: dict) -> None:
    get_table().put_item(Item=to_ddb(item))


def put_if_absent(item: dict) -> bool:
    """Write an item only if one does not already exist at that key.

    Returns True if written, False if an item was already there. This is the
    DynamoDB equivalent of the `MERGE ... WHEN NOT MATCHED THEN INSERT` the SQL
    version used, and it exists for the same reason: a restaurant that already
    carries a cached menu must not have `MenuSourceUrl`/`MenuLastFetchedAt`
    clobbered just because it was geocoded or selected again.
    """
    try:
        get_table().put_item(
            Item=to_ddb(item),
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except get_table().meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True


def get(pk: str, sk: str) -> dict | None:
    response = get_table().get_item(Key={"PK": pk, "SK": sk})
    item = response.get("Item")
    return from_ddb(item) if item else None


def delete(pk: str, sk: str) -> None:
    get_table().delete_item(Key={"PK": pk, "SK": sk})


def query_prefix(pk: str, sk_prefix: str | None = None, limit: int | None = None,
                 ascending: bool = True) -> list[dict]:
    """Query one partition, optionally narrowed to a sort-key prefix.

    Pages until exhausted (or `limit` is reached). DynamoDB's own `Limit` counts
    items *examined* rather than returned, so it is applied here after the fact
    instead - the partitions in this table are small enough that the difference
    costs nothing.
    """
    condition = Key("PK").eq(pk)
    if sk_prefix:
        condition = condition & Key("SK").begins_with(sk_prefix)

    kwargs = {"KeyConditionExpression": condition, "ScanIndexForward": ascending}
    items: list[dict] = []
    while True:
        response = get_table().query(**kwargs)
        items.extend(response.get("Items", []))
        if limit is not None and len(items) >= limit:
            items = items[:limit]
            break
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return [from_ddb(item) for item in items]


def query_range(pk: str, sk_low: str, sk_high: str) -> list[dict]:
    """Query one partition for sort keys within an inclusive range."""
    response_items: list[dict] = []
    kwargs = {"KeyConditionExpression": Key("PK").eq(pk) & Key("SK").between(sk_low, sk_high)}
    while True:
        response = get_table().query(**kwargs)
        response_items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return [from_ddb(item) for item in response_items]


def update(pk: str, sk: str, assignments: dict, condition=None) -> dict | None:
    """SET the given attributes on one item, returning the updated item.

    Attribute names go through the expression-name placeholder map because
    several of ours (`Status`, `Name`, `Role`) are DynamoDB reserved words.
    Returns None when `condition` is supplied and fails.
    """
    if not assignments:
        return get(pk, sk)

    names = {f"#n{i}": key for i, key in enumerate(assignments)}
    values = {f":v{i}": to_ddb(value) for i, value in enumerate(assignments.values())}
    expression = "SET " + ", ".join(
        f"{name} = {value}" for name, value in zip(names, values)
    )

    kwargs = {
        "Key": {"PK": pk, "SK": sk},
        "UpdateExpression": expression,
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": values,
        "ReturnValues": "ALL_NEW",
    }
    if condition is not None:
        kwargs["ConditionExpression"] = condition

    client_errors = get_table().meta.client.exceptions
    try:
        response = get_table().update_item(**kwargs)
    except client_errors.ConditionalCheckFailedException:
        return None
    return from_ddb(response.get("Attributes", {}))


def batch_put(items: list[dict]) -> None:
    """Write many items. Used for menu items and dish elements.

    `batch_writer` handles the 25-item request cap and retries unprocessed items,
    so callers can hand it an arbitrarily long list.
    """
    if not items:
        return
    with get_table().batch_writer() as batch:
        for item in items:
            batch.put_item(Item=to_ddb(item))


def delete_prefix(pk: str, sk_prefix: str) -> int:
    """Delete every item in a partition under a sort-key prefix.

    Used to make the element and menu-item writes idempotent: a retried Step
    Functions task must replace the previous attempt's rows, not append to them.
    Returns the number of items deleted.
    """
    existing = query_prefix(pk, sk_prefix)
    if not existing:
        return 0
    with get_table().batch_writer() as batch:
        for item in existing:
            batch.delete_item(Key={"PK": pk, "SK": item["SK"]})
    return len(existing)
