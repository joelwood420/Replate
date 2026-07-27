import json

import azure.functions as func
import httpx

from shared import places
from shared.auth import get_user_oid

bp = func.Blueprint()


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


@bp.route(route="restaurants/search", methods=["GET"])
def restaurant_search_http(req: func.HttpRequest) -> func.HttpResponse:
    get_user_oid(req)  # same stub-auth pattern as every other endpoint

    result = run(req.params.get("query"), req.params.get("latitude"), req.params.get("longitude"))
    status_code = result.pop("status_code")
    return func.HttpResponse(json.dumps(result), status_code=status_code, mimetype="application/json")
