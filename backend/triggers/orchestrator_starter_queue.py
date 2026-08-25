"""SQS-triggered starter for stage 1.

Was a Durable Functions queue trigger with an injected client; now a Lambda with an
SQS event source mapping that calls StartExecution.

De-duplication carries over unchanged. Durable refused a second `start_new` for an
instance id already running; Step Functions refuses a `StartExecution` for a name
used in the last 90 days. Both mean the same thing here: `POST /jobs/{id}/uploaded`
is not atomic with the send, so two simultaneous calls can both enqueue - and a
duplicate message still cannot double-process the job.
"""

import json

from shared import config, repository, sfn
from shared.models import JobStatus


def _load_job(job_id: str) -> dict:
    job = repository.get_job(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    result = {
        "image_key": job["image_key"],
        "latitude": job.get("latitude"),
        "longitude": job.get("longitude"),
    }
    if job.get("selected_restaurant_id"):
        result["selected_restaurant_id"] = job["selected_restaurant_id"]
    return result


def build_orchestration_input(job_id: str) -> dict:
    job_data = _load_job(job_id)
    repository.update_job(job_id, status=JobStatus.PROCESSING)
    return {"job_id": job_id, **job_data}


def start_for_job(job_id: str) -> bool:
    """Move the job to Processing and start the identify state machine.

    A job cancelled in the brief window between enqueue and this handler running is
    left alone: starting it would undo the cancel and spend model budget the user
    asked to stop. Returns False for that skip, same as an already-running dedupe.
    """
    job = repository.get_job(job_id)
    if job and job.get("status") == JobStatus.CANCELLED:
        return False

    execution_input = build_orchestration_input(job_id)
    return sfn.start_execution(
        config.identify_state_machine_arn(),
        name=sfn.sanitize_name(job_id),
        payload=execution_input,
    )


def handler(event, context=None):
    """SQS event source mapping entry point.

    A batch can contain more than one message. Each is processed independently so
    one bad job id does not fail the whole batch - the raised error would make SQS
    redeliver every message in it, re-running work that already succeeded.
    """
    failures = []
    for record in event.get("Records", []):
        message_id = record.get("messageId")
        try:
            job_id = json.loads(record["body"])["job_id"]
            start_for_job(job_id)
        except Exception:  # noqa: BLE001 - reported per-message, not swallowed
            failures.append({"itemIdentifier": message_id})

    # Partial batch response: only the listed messages are redelivered. Requires
    # ReportBatchItemFailures on the event source mapping in the SAM template.
    return {"batchItemFailures": failures}
