import json

import azure.functions as func

from shared import blob, db
from shared.auth import get_user_oid

bp = func.Blueprint()

DEFAULT_LIMIT = 20


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in ("1", "true", "yes")


def run(user_oid: str, saved: bool | None, limit: int) -> list[dict]:
    query = (
        "SELECT TOP (?) j.JobId, j.Status, j.IsSaved, j.CreatedAt, j.ImageBlobUrl, "
        "jr.DishName, r.Name AS RestaurantName "
        "FROM Jobs j "
        "LEFT JOIN JobResults jr ON jr.JobId = j.JobId "
        "LEFT JOIN Restaurants r ON r.RestaurantId = jr.MatchedRestaurantId "
        "WHERE j.UserId = ?"
    )
    params = [limit, user_oid]
    if saved is not None:
        query += " AND j.IsSaved = ?"
        params.append(1 if saved else 0)
    query += " ORDER BY j.CreatedAt DESC"

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, *params)
        rows = cursor.fetchall()

    return [
        {
            "job_id": str(row.JobId),
            "status": row.Status,
            "is_saved": bool(row.IsSaved),
            "created_at": db.to_utc_iso(row.CreatedAt),
            "dish_name": row.DishName,
            "restaurant_name": row.RestaurantName,
            "image_url": blob.generate_read_sas_url(row.ImageBlobUrl),
        }
        for row in rows
    ]


@bp.route(route="jobs", methods=["GET"])
def jobs_list_http(req: func.HttpRequest) -> func.HttpResponse:
    user_oid = get_user_oid(req)
    saved = _parse_bool(req.params.get("saved"))
    try:
        limit = int(req.params.get("limit", DEFAULT_LIMIT))
    except ValueError:
        limit = DEFAULT_LIMIT

    jobs = run(user_oid, saved, limit)
    return func.HttpResponse(json.dumps(jobs), status_code=200, mimetype="application/json")
