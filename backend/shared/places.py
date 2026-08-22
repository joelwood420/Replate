import math

import httpx

from shared import config

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location"
LOCATION_BIAS_RADIUS_M = 5000.0

# GPS -> nearby restaurants via OpenStreetMap's Overpass API. Chosen over Google Places
# because it needs no API key and no billing account (see docs/decisions.md, 2026-08-22).
# The public instance is fair-use, so send a descriptive User-Agent per the OSM policy.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_USER_AGENT = "Replate/1.0 (dish identification; https://github.com/joelwood420/Replate)"
NEARBY_RADIUS_M = 250
# OSM amenity tags for "a place you would photograph a dish at".
_FOOD_AMENITIES = ("restaurant", "cafe", "fast_food", "bar", "pub", "bistro")


class PlacesError(Exception):
    """A nearby-restaurant lookup failed transiently; the caller may fall back."""


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


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres, so candidates can be sorted nearest-first."""
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _osm_address(tags: dict) -> str | None:
    street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p)
    address = ", ".join(p for p in (street, tags.get("addr:city")) if p)
    return address or None


def _overpass_query(latitude: float, longitude: float, radius_m: int) -> str:
    clauses = "".join(
        f'node["amenity"="{amenity}"](around:{radius_m},{latitude},{longitude});'
        f'way["amenity"="{amenity}"](around:{radius_m},{latitude},{longitude});'
        for amenity in _FOOD_AMENITIES
    )
    # `out center` gives ways (building polygons) a single lat/lon like nodes have.
    return f"[out:json][timeout:25];({clauses});out center tags;"


def nearby_restaurants(latitude: float, longitude: float, radius_m: int = NEARBY_RADIUS_M) -> list[dict]:
    """Restaurants near a GPS point, from OpenStreetMap's Overpass API.

    Free and key-less (chosen over Google Places to avoid a billing account, see
    docs/decisions.md). Returns candidates sorted nearest-first in the same shape the
    geocode activity persists. Raises PlacesError on a transport or HTTP failure so the
    caller can fall back; an empty list means the call worked but found nothing nearby.
    """
    query = _overpass_query(latitude, longitude, radius_m)
    try:
        response = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": OVERPASS_USER_AGENT},
            timeout=config.places_timeout_seconds(),
        )
        response.raise_for_status()
        elements = response.json().get("elements", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise PlacesError(f"Overpass lookup failed: {exc}") from exc

    candidates = []
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # an unnamed POI cannot identify a restaurant
        center = element.get("center", {})
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        if lat is None or lon is None:
            continue
        candidates.append(
            {
                "restaurant_id": f"osm-{element['type']}-{element['id']}",
                "name": name,
                "address": _osm_address(tags),
                "latitude": lat,
                "longitude": lon,
                "distance_m": round(_haversine_m(latitude, longitude, lat, lon)),
                "menu_source_url": tags.get("website") or tags.get("contact:website"),
            }
        )
    return sorted(candidates, key=lambda c: c["distance_m"])
