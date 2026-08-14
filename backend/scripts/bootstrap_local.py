"""Create every local AWS resource the app needs, against LocalStack.

Replaces `apply_schema.py` plus `configure_azurite_cors.py`. Idempotent - safe to
re-run after `docker compose down`, and safe to run before LocalStack has finished
starting only in the sense that it will fail loudly rather than half-create things.

In a deployed environment none of this runs: the table, bucket and queue all come
from the SAM template (Phase 3).

Run directly: `python scripts/bootstrap_local.py` (from backend/).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.create_table import create_table  # noqa: E402
from shared import config, queue, storage  # noqa: E402


def create_bucket() -> str:
    """Create the uploads bucket and allow browser PUTs to it.

    The CORS rule is the S3 equivalent of what configure_azurite_cors.py did for
    Azurite: without it the browser's preflight against the presigned URL fails and
    the upload never leaves the page. Deployed, the same rule is set by the SAM
    template - and there it should list the real site origin rather than "*".
    """
    bucket = config.s3_bucket_uploads()
    client = storage.get_client()

    existing = {entry["Name"] for entry in client.list_buckets().get("Buckets", [])}
    if bucket in existing:
        message = f"Bucket '{bucket}' already exists."
    else:
        kwargs = {"Bucket": bucket}
        region = config.aws_region()
        # us-east-1 is the one region that rejects an explicit location constraint.
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**kwargs)
        message = f"Created bucket '{bucket}'."

    client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": ["*"],
                    "AllowedMethods": ["PUT", "GET", "HEAD"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        },
    )
    return f"{message} CORS configured for local dev (all origins)."


def create_queue() -> str:
    url = queue._ensure_queue()
    return f"Queue ready at {url}"


def main() -> None:
    for step in (create_table, create_bucket, create_queue):
        print(step())


if __name__ == "__main__":
    main()
