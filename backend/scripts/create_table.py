"""Create the local DynamoDB table.

Replaces `apply_schema.py` and `db/schema.sql`. In a deployed environment the
table is defined by the SAM template (Phase 3) and this script is never run - it
exists so local dev and CI can stand up the same shape without duplicating a
schema file that could drift.

The table itself is nearly shapeless: one partition key, one sort key, and a TTL
attribute. Everything that used to be eleven CREATE TABLE statements is now a key
convention, documented in `shared/ddb.py`.

Run directly: `python scripts/create_table.py` (from backend/), with
AWS_ENDPOINT_URL pointing at LocalStack or DynamoDB Local.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import config, ddb  # noqa: E402

# Provisioned, not on-demand, and at or below the perpetual free-tier grant of 25
# read + 25 write capacity units. On-demand tables bill per request from the very
# first request - see CLAUDE.md Global Rule 1. Local emulators ignore this, but
# keeping it identical to the deployed setting means the local table is not a
# subtly different thing from the real one.
READ_CAPACITY = 5
WRITE_CAPACITY = 5


def create_table() -> str:
    table_name = config.ddb_table_name()
    client = ddb.client()

    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        return f"Table '{table_name}' already exists - nothing to do."

    client.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        ProvisionedThroughput={
            "ReadCapacityUnits": READ_CAPACITY,
            "WriteCapacityUnits": WRITE_CAPACITY,
        },
    )
    client.get_waiter("table_exists").wait(TableName=table_name)

    # Rate-limit buckets self-expire. TTL deletion is best-effort and can lag by
    # up to ~48 hours, which is why shared/rate_limit.py still bounds its reads by
    # an explicit key range rather than trusting the table to be clean.
    client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"},
    )

    return f"Created table '{table_name}' with TTL on 'expires_at'."


if __name__ == "__main__":
    print(create_table())
