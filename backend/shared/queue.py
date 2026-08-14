"""SQS job queue.

Replaces Azure Queue Storage. The message body is the same plain JSON it always
was - notably, none of the base64 encoding trouble that Azure Queue Storage
needed `messageEncoding: none` in host.json to work around. SQS message bodies
are just strings.

The queue is addressed by URL rather than by name. In a deployed environment that
URL comes from the SAM template as an environment variable; locally it is
LocalStack's. `_ensure_queue` exists only for the local case, where nothing has
created the queue ahead of time.
"""

import json
import threading

import boto3

from shared import config

_lock = threading.Lock()
_client = None


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                kwargs = {"region_name": config.aws_region()}
                endpoint = config.aws_endpoint_url()
                if endpoint:
                    kwargs["endpoint_url"] = endpoint
                _client = boto3.client("sqs", **kwargs)
    return _client


def reset_client_cache() -> None:
    global _client
    with _lock:
        _client = None


def _ensure_queue() -> str:
    """Return the queue URL, creating the queue if it does not exist.

    Only meaningful against LocalStack. In a real deployment the queue is created
    by the SAM template and SQS_QUEUE_URL points at it, so `create_queue` is never
    reached - and it is idempotent anyway, returning the existing URL for a queue
    that is already there.
    """
    configured = config.sqs_queue_url()
    if configured:
        return configured
    return get_client().create_queue(QueueName=config.sqs_queue_name())["QueueUrl"]


def send_job_message(job_id: str) -> None:
    get_client().send_message(QueueUrl=_ensure_queue(), MessageBody=json.dumps({"job_id": job_id}))


def decode_job_message(message_content: str) -> dict:
    return json.loads(message_content)
