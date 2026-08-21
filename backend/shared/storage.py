"""S3 object storage - presigned upload and read URLs.

Replaces the Azure Blob Storage layer. The shape is the same: the API hands the
client a short-lived write-only URL, the client PUTs the photo straight to
storage without it passing through the backend, and reads later go through a
short-lived read URL.

One real improvement over the Azure version. Generating a blob SAS required the
storage account key, so `shared/blob.py` reached into
`service_client.credential.account_key` - a long-lived shared secret the function
had to hold. A presigned S3 URL is signed with whatever credentials the caller
already has, which in a deployed environment is the Lambda's execution role. No
stored key, nothing to rotate.

Jobs store the **object key** (`uploads/<uuid>.jpg`), not a URL. The Azure code
stored a full blob URL and parsed the blob name back out of it on every read;
the key is the stable identifier and the URL is derived, so storing the key is
both simpler and immune to the bucket or region changing.
"""

import datetime
import threading
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from shared import config as app_config

UPLOAD_PREFIX = "uploads/"

_lock = threading.Lock()
_client = None


def get_client():
    """The shared S3 client, created on first use and cached per process."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                kwargs = {
                    "region_name": app_config.aws_region(),
                    # SigV4 explicitly: presigned URLs signed with the older V2
                    # scheme are rejected by buckets in regions created after 2014.
                    "config": Config(signature_version="s3v4"),
                }
                endpoint = app_config.aws_endpoint_url()
                if endpoint:
                    kwargs["endpoint_url"] = endpoint
                    # LocalStack does not resolve virtual-host-style bucket
                    # subdomains, so force path-style addressing there.
                    kwargs["config"] = Config(
                        signature_version="s3v4", s3={"addressing_style": "path"}
                    )
                _client = boto3.client("s3", **kwargs)
    return _client


def reset_client_cache() -> None:
    """Drop the cached client. For tests and endpoint changes between runs."""
    global _client
    with _lock:
        _client = None


def _expiry_seconds() -> int:
    return app_config.presigned_url_expiry_minutes() * 60


def generate_upload_url(key: str | None = None) -> dict:
    """Mint a short-lived write-only URL for the client to PUT its photo to.

    Only reserves a name - no object exists until the client actually uploads,
    which is why `POST /api/jobs` does not enqueue anything and the client has to
    call the separate `uploaded` endpoint afterwards.
    """
    key = key or f"{UPLOAD_PREFIX}{uuid.uuid4()}.jpg"
    expiry_seconds = _expiry_seconds()

    upload_url = get_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": app_config.s3_bucket_uploads(), "Key": key},
        ExpiresIn=expiry_seconds,
    )
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=expiry_seconds
    )

    return {"key": key, "upload_url": upload_url, "expiry": expires_at.isoformat()}


def generate_read_url(key: str) -> str:
    """Mint a short-lived read-only URL for an object previously uploaded.

    The upload URL is write-only, so a stored key is not browser-readable without
    this. The bucket itself stays private - there is no public-read ACL anywhere.
    """
    return get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": app_config.s3_bucket_uploads(), "Key": key},
        ExpiresIn=_expiry_seconds(),
    )


def read_object(key: str) -> tuple[bytes, str]:
    """Read an uploaded object's bytes and content type.

    Used by the vision guess to pull the photo into the Lambda and base64-encode
    it for the model - unlike moderation, which hands Rekognition an S3 reference
    and never sees the bytes. Returns the object's stored ContentType so the caller
    can pick the right image media type, defaulting to JPEG (what the uploads are).
    """
    response = get_client().get_object(Bucket=app_config.s3_bucket_uploads(), Key=key)
    body = response["Body"].read()
    return body, response.get("ContentType") or "image/jpeg"


def object_exists(key: str) -> bool:
    """Whether the client has actually uploaded to a key we handed out.

    `generate_upload_url` only reserves a name; the object does not exist until
    the client PUTs to it, and it may never do so if the upload fails or the app
    is closed mid-upload. Image moderation checks this before reading.
    """
    try:
        get_client().head_object(Bucket=app_config.s3_bucket_uploads(), Key=key)
    except ClientError as exc:
        # 404 is "not uploaded"; 403 is what a bucket without ListBucket returns
        # for a missing key, so it means the same thing here. Anything else is a
        # real failure and should not be silently reported as "missing".
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in (403, 404):
            return False
        raise
    return True
