import json
import uuid

import azure.functions as func

from shared import blob, config, db, queue
from shared.models import JobStatus

bp = func.Blueprint()


def get_user_oid(req: func.HttpRequest) -> str:
    header_name = config.stub_auth_header_name()
    return req.headers.get(header_name) or config.stub_default_user_oid()


def validate_body(body: dict) -> str | None:
    if "latitude" not in body or "longitude" not in body:
        return "latitude and longitude are required"
    try:
        float(body["latitude"])
        float(body["longitude"])
    except (TypeError, ValueError):
        return "latitude and longitude must be numbers"
    return None


def _create_job(user_oid: str, latitude: float, longitude: float, blob_url: str, conn) -> str:
    job_id = str(uuid.uuid4())
    cursor = conn.cursor()
    cursor.execute(
        "MERGE Users AS target USING (SELECT ? AS UserId) AS src ON target.UserId = src.UserId "
        "WHEN NOT MATCHED THEN INSERT (UserId) VALUES (?);",
        user_oid,
        user_oid,
    )
    cursor.execute(
        "INSERT INTO Jobs (JobId, UserId, Status, ImageBlobUrl, Latitude, Longitude) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        job_id,
        user_oid,
        JobStatus.QUEUED,
        blob_url,
        latitude,
        longitude,
    )
    return job_id


def run(body: dict, user_oid: str) -> dict:
    error = validate_body(body)
    if error:
        return {"error": error}

    latitude = float(body["latitude"])
    longitude = float(body["longitude"])

    upload_info = blob.generate_upload_sas_url()

    with db.get_connection() as conn:
        job_id = _create_job(user_oid, latitude, longitude, upload_info["blob_url"], conn)

    queue.send_job_message(job_id)

    return {"job_id": job_id, "upload_url": upload_info["sas_url"], "blob_url": upload_info["blob_url"]}


@bp.route(route="jobs", methods=["POST"])
def upload_http(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    result = run(body, get_user_oid(req))

    if "error" in result:
        return func.HttpResponse(json.dumps(result), status_code=400, mimetype="application/json")
    return func.HttpResponse(json.dumps(result), status_code=201, mimetype="application/json")
