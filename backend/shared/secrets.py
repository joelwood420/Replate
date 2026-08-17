"""Read SecureString secrets from SSM Parameter Store at runtime.

The Anthropic API key is the one stored credential the model calls introduce
(docs/decisions.md, 2026-08-17). It lives in Parameter Store as a SecureString -
CloudFormation can't create SecureStrings, so it is put there by hand
(`aws ssm put-parameter --name /replate/anthropic-api-key --type SecureString ...`)
and the Lambda's execution role is granted `ssm:GetParameter` on `replate/*`.

Values are cached for the life of the Lambda container: a warm invocation reads
the decrypted value from memory, not from SSM, so this costs one GetParameter per
cold start rather than one per request. A rotated secret is picked up when the
container is recycled - acceptable, and the alternative (fetching per request)
would add latency and SSM calls to every job. Only successful reads are cached,
so a transient SSM error is retried on the next call.
"""

import threading

import boto3

from shared import config

_lock = threading.Lock()
_client = None
_cache: dict[str, str] = {}


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                kwargs = {"region_name": config.aws_region()}
                endpoint = config.aws_endpoint_url()
                if endpoint:
                    kwargs["endpoint_url"] = endpoint
                _client = boto3.client("ssm", **kwargs)
    return _client


def reset_caches() -> None:
    """Drop the client and value caches - for tests."""
    global _client
    with _lock:
        _client = None
        _cache.clear()


def get_secure_parameter(name: str) -> str:
    """Return a decrypted SecureString value, cached per parameter name.

    Raises on an SSM error (missing parameter, access denied, service error) so
    the caller can decide how to handle it - `anthropic_client` degrades to the
    no-key path, matching the blank-key stub posture.
    """
    cached = _cache.get(name)
    if cached is not None:
        return cached

    with _lock:
        cached = _cache.get(name)
        if cached is not None:
            return cached
        response = get_client().get_parameter(Name=name, WithDecryption=True)
        value = response["Parameter"]["Value"]
        _cache[name] = value
        return value
