"""POST /api/jobs - reserve an upload slot and create the job row.

Deliberately does NOT enqueue the job. The client only uploads the photo after this
call returns the SAS URL, so enqueuing here raced the upload - the orchestrator could
start, and try to read the blob, before the image existed. The client signals it has
finished via POST /api/jobs/{jobId}/uploaded instead (triggers/job_uploaded_http.py).
"""

import json
import uuid

import azure.functions as func

from shared import blob, rate_limit, repository
from shared.auth import get_user_oid
from shared.models import JobStatus

bp = func.Blueprint()

_SELECTED_RESTAURANT_REQUIRED_FIELDS = ("place_id", "name", "latitude", "longitude")


def validate_body(body: dict) -> str | None:
    has_gps = "latitude" in body and "longitude" in body
    has_selected = "selected_restaurant" in body

    if has_gps and has_selected:
        return "provide either latitude/longitude or selected_restaurant, not both"

    if has_gps:
        try:
            float(body["latitude"])
            float(body["longitude"])
        except (TypeError, ValueError):
            return "latitude and longitude must be numbers"
        return None

    if has_selected:
        selected = body["selected_restaurant"]
        if not isinstance(selected, dict):
            return "selected_restaurant must be an object"
        for field in _SELECTED_RESTAURANT_REQUIRED_FIELDS:
            if field not in selected:
                return f"selected_restaurant.{field} is required"
        try:
            float(selected["latitude"])
            float(selected["longitude"])
        except (TypeError, ValueError):
            return "selected_restaurant latitude/longitude must be numbers"
        return None

    return "latitude/longitude or selected_restaurant is required"


def _insert_job(
    user_oid: str, latitude: float, longitude: float, selected_restaurant_id: str | None, image_key: str
) -> str:
    job_id = str(uuid.uuid4())
    repository.create_job(
        job_id=job_id,
        user_oid=user_oid,
        status=JobStatus.QUEUED,
        image_key=image_key,
        latitude=latitude,
        longitude=longitude,
        selected_restaurant_id=selected_restaurant_id,
    )
    return job_id


def _create_job(user_oid: str, body: dict, image_key: str) -> str:
    if "selected_restaurant" in body:
        selected = body["selected_restaurant"]
        latitude = float(selected["latitude"])
        longitude = float(selected["longitude"])
        restaurant_id = selected["place_id"]
        # The restaurant item is written first so the menu-fetch step later in the
        # pipeline has a record to hang MenuLastFetchedAt on. There is no foreign
        # key enforcing this any more, but the ordering still matters.
        repository.upsert_restaurant(
            restaurant_id, selected["name"], selected.get("address", ""), latitude, longitude, None
        )
        return _insert_job(user_oid, latitude, longitude, restaurant_id, image_key)

    latitude = float(body["latitude"])
    longitude = float(body["longitude"])
    return _insert_job(user_oid, latitude, longitude, None, image_key)


def run(body: dict, user_oid: str) -> dict:
    error = validate_body(body)
    if error:
        return {"status_code": 400, "body": {"error": error}}

    # Minted before the quota check. It costs nothing to throw away on a throttled
    # request - the URL is signed locally from the caller's own credentials, and the
    # object it names is never created unless the client uploads to it.
    upload_info = blob.generate_upload_sas_url()

    repository.ensure_user(user_oid)

    quota = rate_limit.check_and_consume(user_oid, rate_limit.Action.SCAN)
    if not quota["allowed"]:
        return {
            "status_code": 429,
            "body": {"error": quota["error"], "retry_after_seconds": quota["retry_after_seconds"]},
            "headers": {"Retry-After": str(quota["retry_after_seconds"])},
        }

    job_id = _create_job(user_oid, body, upload_info["blob_url"])

    return {
        "status_code": 201,
        "body": {
            "job_id": job_id,
            "upload_url": upload_info["sas_url"],
            "blob_url": upload_info["blob_url"],
        },
    }


@bp.route(route="jobs", methods=["POST"])
def upload_http(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    outcome = run(body, get_user_oid(req))

    return func.HttpResponse(
        json.dumps(outcome["body"]),
        status_code=outcome["status_code"],
        mimetype="application/json",
        headers=outcome.get("headers"),
    )
