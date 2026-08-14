import json

import azure.durable_functions as df

from shared import config, repository
from shared.models import JobStatus

bp = df.Blueprint()


def _load_job(job_id: str) -> dict:
    job = repository.get_job(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    result = {
        "image_blob_url": job["image_key"],
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


async def handle_queue_message(message_body: bytes, client) -> None:
    job_id = json.loads(message_body.decode("utf-8"))["job_id"]
    orchestration_input = build_orchestration_input(job_id)
    await client.start_new("dish_orchestrator_trigger", instance_id=job_id, client_input=orchestration_input)


@bp.queue_trigger(arg_name="msg", queue_name=config.queue_name_jobs(), connection="AzureWebJobsStorage")
@bp.durable_client_input(client_name="client")
async def orchestrator_starter_queue(msg, client) -> None:
    await handle_queue_message(msg.get_body(), client)
