import httpx

from shared import http, places
from shared.auth import get_user_oid


def run(query: str | None, latitude: str | None, longitude: str | None) -> dict:
    if not query or not query.strip():
        return {"error": "query is required", "status_code": 400}

    lat = float(latitude) if latitude else None
    lon = float(longitude) if longitude else None

    try:
        restaurants = places.search_restaurants(query.strip(), lat, lon)
    except httpx.HTTPError:
        return {"error": "restaurant search is temporarily unavailable", "status_code": 502}

    return {"restaurants": restaurants, "status_code": 200}


def handler(event, context=None):
    """GET /api/restaurants/search?query=&latitude=&longitude="""
    get_user_oid(event)  # same stub-auth pattern as every other endpoint

    result = run(
        http.query_param(event, "query"),
        http.query_param(event, "latitude"),
        http.query_param(event, "longitude"),
    )
    return http.respond(result.pop("status_code"), result)
