"""Step Functions client - starting executions.

Replaces the Durable Functions client that `orchestrator_starter_queue.py` and
`recipe_starter_http.py` got injected via `@bp.durable_client_input`.

Execution names carry the same de-duplication role Durable's `instance_id` did.
Step Functions rejects a `StartExecution` whose name matches an execution created
in the last 90 days, which is exactly the property both callers relied on: a
duplicated queue message or a double-tapped button cannot start the pipeline
twice. `ExecutionAlreadyExists` is therefore an expected outcome, not an error.
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
                _client = boto3.client("stepfunctions", **kwargs)
    return _client


def reset_client_cache() -> None:
    global _client
    with _lock:
        _client = None


def start_execution(state_machine_arn: str, name: str, payload: dict) -> bool:
    """Start an execution. Returns False if one with this name already exists.

    A False return is not a failure - it means the work is already in flight or
    done, and the caller should treat the request as accepted.
    """
    client = get_client()
    try:
        client.start_execution(
            stateMachineArn=state_machine_arn,
            name=name,
            input=json.dumps(payload),
        )
    except client.exceptions.ExecutionAlreadyExists:
        return False
    return True


def sanitize_name(raw: str) -> str:
    """Make a string safe to use as an execution name.

    Step Functions allows up to 80 characters and forbids whitespace, wildcards,
    bracket, and control characters. Job ids are UUIDs and the recipe suffix uses
    a colon, which is not permitted - hence the substitution.
    """
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in raw)
    return cleaned[:80]
