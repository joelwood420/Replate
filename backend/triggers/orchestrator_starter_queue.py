import json

import azure.durable_functions as df

from shared import config, db
from shared.models import JobStatus

bp = df.Blueprint()


def _load_job(job_id: str, conn) -> dict:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ImageBlobUrl, Latitude, Longitude, SelectedRestaurantId FROM Jobs WHERE JobId = ?", job_id
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Job not found: {job_id}")
    result = {
        "image_blob_url": row.ImageBlobUrl,
        "latitude": float(row.Latitude),
        "longitude": float(row.Longitude),
    }
    if row.SelectedRestaurantId:
        result["selected_restaurant_id"] = row.SelectedRestaurantId
    return result


def _mark_processing(job_id: str, conn) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Jobs SET Status = ?, UpdatedAt = SYSUTCDATETIME() WHERE JobId = ?",
        JobStatus.PROCESSING,
        job_id,
    )


def build_orchestration_input(job_id: str) -> dict:
    with db.get_connection() as conn:
        job_data = _load_job(job_id, conn)
        _mark_processing(job_id, conn)
    return {"job_id": job_id, **job_data}


async def handle_queue_message(message_body: bytes, client) -> None:
    job_id = json.loads(message_body.decode("utf-8"))["job_id"]
    orchestration_input = build_orchestration_input(job_id)
    await client.start_new("dish_orchestrator_trigger", instance_id=job_id, client_input=orchestration_input)


@bp.queue_trigger(arg_name="msg", queue_name=config.queue_name_jobs(), connection="AzureWebJobsStorage")
@bp.durable_client_input(client_name="client")
async def orchestrator_starter_queue(msg, client) -> None:
    await handle_queue_message(msg.get_body(), client)
