import httpx

from shared import config

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location"
LOCATION_BIAS_RADIUS_M = 5000.0


def _to_candidate(place: dict) -> dict:
    location = place.get("location", {})
    return {
        "place_id": place["id"],
        "name": place.get("displayName", {}).get("text", ""),
        "address": place.get("formattedAddress", ""),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
    }


def search_restaurants(query: str, latitude: float | None, longitude: float | None) -> list[dict]:
    body: dict = {"textQuery": query, "includedType": "restaurant"}
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": LOCATION_BIAS_RADIUS_M}
        }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": config.google_places_api_key(),
        "X-Goog-FieldMask": FIELD_MASK,
    }
    response = httpx.post(PLACES_SEARCH_URL, json=body, headers=headers, timeout=config.places_timeout_seconds())
    response.raise_for_status()
    return [_to_candidate(place) for place in response.json().get("places", [])]
