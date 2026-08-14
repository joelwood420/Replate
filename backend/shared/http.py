"""API Gateway HTTP API (payload format 2.0) request/response adapters.

Replaces the `azure.functions` HttpRequest/HttpResponse layer. Everything here is
mechanical translation - the handlers stay thin adapters over the `run()`
functions, which is what keeps the business logic testable without constructing
gateway events.

Response shape is always `{statusCode, headers, body}` with a JSON-serialised
body. Returning a dict from a Lambda behind an HTTP API would be auto-serialised
into a 200, which silently loses non-200 status codes - so every path here is
explicit.
"""

import base64
import json


def get_body(event: dict) -> dict:
    """Parse the request body as JSON, tolerating an absent or malformed one.

    Matches the old behaviour: `req.get_json()` raising ValueError was caught and
    treated as an empty body, letting validation produce a 400 with a useful
    message rather than a 500.
    """
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def path_param(event: dict, name: str) -> str | None:
    return (event.get("pathParameters") or {}).get(name)


def query_param(event: dict, name: str, default=None):
    return (event.get("queryStringParameters") or {}).get(name, default)


def get_header(event: dict, name: str) -> str | None:
    """Case-insensitive header lookup.

    API Gateway lower-cases header names in payload format 2.0, but not every
    local emulator does, so this does not rely on it.
    """
    headers = event.get("headers") or {}
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def respond(status_code: int, body, headers: dict | None = None) -> dict:
    response = {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(body),
    }
    return response


def from_outcome(outcome: dict) -> dict:
    """Turn a `run()` outcome into a gateway response.

    `run()` functions return `{"status_code": ..., "body": ..., "headers": ...}`,
    which is deliberately transport-agnostic - it was the same shape under Azure
    Functions and survived the port untouched.
    """
    return respond(outcome["status_code"], outcome["body"], outcome.get("headers"))
