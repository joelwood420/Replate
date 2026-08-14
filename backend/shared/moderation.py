"""Image moderation via Amazon Rekognition.

Called on the uploaded photo before anything else in the pipeline, so a rejected
image costs one moderation call and no model spend at all.

FAILURE MODE (decision of 2026-08-05, see docs/decisions.md) - carried over from
the Azure Content Safety implementation unchanged, because the reasoning is not
cloud-specific: an explicit unsafe verdict blocks the job, but a service error,
timeout, missing configuration or exhausted quota does not. "This image is
unsafe" and "I could not check this image" are different answers and are
reported as different verdicts.

Two things got better in the move. Rekognition reads the object straight out of
S3, so there is no presigned URL round-trip and the image never leaves the AWS
account - the Azure service had to fetch the blob over the public internet with a
SAS attached, which is also why moderation could never work against Azurite
locally. And there is no API key: the Lambda's execution role authorises the call.
"""

import logging
import threading

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from shared import config as app_config

_lock = threading.Lock()
_client = None


class Verdict:
    SAFE = "safe"
    UNSAFE = "unsafe"
    #: The check did not complete. Callers allow these through - see the module docstring.
    UNCHECKED = "unchecked"


#: Errors where retrying cannot help: the request or the permissions are wrong,
#: not the service. Mirrors the old "don't retry a 4xx" rule.
_FATAL_ERROR_CODES = {
    "AccessDeniedException",
    "InvalidImageFormatException",
    "InvalidParameterException",
    "InvalidS3ObjectException",
    "ImageTooLargeException",
}


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                kwargs = {
                    "region_name": app_config.aws_region(),
                    "config": Config(retries={"max_attempts": 1, "mode": "standard"}),
                }
                endpoint = app_config.aws_endpoint_url()
                if endpoint:
                    kwargs["endpoint_url"] = endpoint
                _client = boto3.client("rekognition", **kwargs)
    return _client


def reset_client_cache() -> None:
    global _client
    with _lock:
        _client = None


def is_configured() -> bool:
    return app_config.moderation_enabled()


def _unchecked(detail: str) -> dict:
    logging.warning("Moderation check did not complete, allowing image through: %s", detail)
    return {"verdict": Verdict.UNCHECKED, "categories": [], "detail": detail}


def analyze_image(image_key: str) -> dict:
    """Moderate an object in the uploads bucket, by key.

    Returns `{"verdict": ..., "categories": [...], "detail": ...}`, where
    `categories` lists the labels that met the confidence threshold (only ever
    populated on an unsafe verdict).
    """
    if not is_configured():
        return _unchecked("MODERATION_ENABLED is not set")

    request = {
        "Image": {
            "S3Object": {"Bucket": app_config.s3_bucket_uploads(), "Name": image_key}
        },
        "MinConfidence": app_config.moderation_min_confidence(),
    }

    last_error = "no attempts were made"
    for _ in range(app_config.moderation_max_retries() + 1):
        try:
            response = get_client().detect_moderation_labels(**request)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            last_error = f"{code}: {exc}"
            # Throttling and service faults are worth another go; a malformed
            # request or a missing permission is not.
            if code in _FATAL_ERROR_CODES:
                break
            continue
        except BotoCoreError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        labels = response.get("ModerationLabels", [])
        if labels:
            # Report top-level categories where Rekognition gives them - a label of
            # "Explicit Nudity" under parent "Nudity" reads better as the parent.
            categories = sorted(
                {label.get("ParentName") or label.get("Name", "Unknown") for label in labels}
            )
            return {"verdict": Verdict.UNSAFE, "categories": categories, "detail": None}

        return {"verdict": Verdict.SAFE, "categories": [], "detail": None}

    return _unchecked(last_error)
