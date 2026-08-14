from shared import http, repository, storage
from shared.auth import get_user_oid

DEFAULT_LIMIT = 20


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in ("1", "true", "yes")


def run(user_oid: str, saved: bool | None, limit: int) -> list[dict]:
    """The cookbook listing.

    This was a three-table join (Jobs -> JobResults -> Restaurants) to get a dish
    name and restaurant name per row. It is now a single query against the user's
    partition: `dish_name` and `restaurant_name` are denormalised onto the listing
    item when stage 1 persists the match. See `shared/repository.py` for how the
    two copies are kept in step.
    """
    jobs = repository.list_jobs(user_oid, saved=saved, limit=limit)
    return [
        {
            "job_id": job["job_id"],
            "status": job["status"],
            "is_saved": bool(job.get("is_saved")),
            "created_at": job["created_at"],
            "dish_name": job.get("dish_name"),
            "restaurant_name": job.get("restaurant_name"),
            "image_url": storage.generate_read_url(job["image_key"]),
        }
        for job in jobs
    ]


def handler(event, context=None):
    """GET /api/jobs?saved=&limit="""
    saved = _parse_bool(http.query_param(event, "saved"))
    try:
        limit = int(http.query_param(event, "limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT

    return http.respond(200, run(get_user_oid(event), saved, limit))
