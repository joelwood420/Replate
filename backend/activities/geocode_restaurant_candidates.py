"""Reverse-geocode the uploaded GPS to nearby restaurant candidates.

Was a canned stub. Now uses OpenStreetMap's Overpass API (free, no API key, no
billing account, unlike Google Places, see docs/decisions.md 2026-08-22), with a
best-effort Claude web_search fallback when Overpass is unavailable or finds
nothing. No candidates at all is a valid outcome, not an error: it produces the
vision-only low-confidence match downstream.
"""

import hashlib

from shared import anthropic_client, config, models, places, repository

#: The (0, 0) sentinel for "no usable GPS". Short-circuited so a job without
#: coordinates never makes a network call.
NULL_ISLAND = (0.0, 0.0)

_CLAUDE_NEARBY_SYSTEM = (
    "You find real, currently-operating restaurants near a set of GPS coordinates. Use the "
    "web_search tool. Return only real places, closest first."
)


def _persist(job_id: str, candidates: list[dict]) -> None:
    for candidate in candidates:
        repository.upsert_restaurant(
            candidate["restaurant_id"],
            candidate["name"],
            candidate["address"],
            candidate["latitude"],
            candidate["longitude"],
            candidate["menu_source_url"],
        )
    repository.put_job_candidates(job_id, candidates)


def _claude_nearby(latitude: float, longitude: float) -> list[dict]:
    """Fallback when Overpass fails or returns nothing.

    Uses the Anthropic web_search tool already wired for menu fetch. Coordinates are a weak
    query for a search engine, so this is a backstop, not the primary path: any failure or
    unparseable reply just yields no candidates, which is a valid vision-only outcome.
    """
    model = config.anthropic_menu_model()
    if not (model and anthropic_client.is_configured()):
        return []

    prompt = (
        f"Find up to 5 real restaurants closest to latitude {latitude}, longitude {longitude}. "
        'Return ONLY a JSON object of the form {"restaurants": [{"name": ..., "address": ..., '
        '"latitude": ..., "longitude": ..., "website": ...}]}. Use null for anything unknown.'
    )
    try:
        raw = anthropic_client.web_search_completion(
            model=model,
            system=_CLAUDE_NEARBY_SYSTEM,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
        data = anthropic_client.parse_json_response(raw)
    except (anthropic_client.AnthropicError, ValueError):
        return []

    candidates = []
    for restaurant in data.get("restaurants", []):
        name = restaurant.get("name")
        if not name:
            continue
        candidates.append(
            {
                # No stable OSM id here, so derive a deterministic one from the name.
                "restaurant_id": "claude-" + hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:12],
                "name": name,
                "address": restaurant.get("address"),
                "latitude": restaurant.get("latitude"),
                "longitude": restaurant.get("longitude"),
                # A text search cannot give a reliable distance; the model is asked to
                # return closest-first, so order stands in for it.
                "distance_m": None,
                "menu_source_url": restaurant.get("website"),
            }
        )
    return candidates


def run(activity_input: dict) -> list[dict]:
    latitude = activity_input["latitude"]
    longitude = activity_input["longitude"]
    if (latitude, longitude) == NULL_ISLAND:
        return []

    try:
        candidates = places.nearby_restaurants(latitude, longitude)
    except places.PlacesError:
        candidates = []
    if not candidates:
        candidates = _claude_nearby(latitude, longitude)

    if candidates:
        _persist(activity_input["job_id"], candidates)
    return candidates


def handler(event, context=None):
    """Lambda entry point for the GeocodeRestaurantCandidates task.

    Wraps the plain list `run` returns in the envelope the state machine's
    Choice state reads - see `shared.models.candidate_envelope`.
    """
    return models.candidate_envelope(run(event))
