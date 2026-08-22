from unittest.mock import MagicMock

import httpx
import pytest

from shared import places


def _mock_response(json_body: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_body
    response.raise_for_status.return_value = None
    return response


def test_search_restaurants_builds_request_without_location_bias(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _mock_response({"places": []})

    monkeypatch.setattr(places.httpx, "post", fake_post)

    places.search_restaurants("Luigi's", None, None)

    assert captured["url"] == places.PLACES_SEARCH_URL
    assert captured["json"] == {"textQuery": "Luigi's", "includedType": "restaurant"}
    assert captured["headers"]["X-Goog-FieldMask"] == places.FIELD_MASK


def test_search_restaurants_includes_location_bias_when_coords_given(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return _mock_response({"places": []})

    monkeypatch.setattr(places.httpx, "post", fake_post)

    places.search_restaurants("Luigi's", 40.7128, -74.0060)

    assert captured["json"]["locationBias"] == {
        "circle": {"center": {"latitude": 40.7128, "longitude": -74.0060}, "radius": places.LOCATION_BIAS_RADIUS_M}
    }


def test_search_restaurants_parses_response_into_candidates(monkeypatch):
    canned = {
        "places": [
            {
                "id": "place-1",
                "displayName": {"text": "Luigi's"},
                "formattedAddress": "123 Main St",
                "location": {"latitude": 40.7, "longitude": -74.0},
            }
        ]
    }
    monkeypatch.setattr(places.httpx, "post", lambda *a, **k: _mock_response(canned))

    result = places.search_restaurants("Luigi's", None, None)

    assert result == [
        {"place_id": "place-1", "name": "Luigi's", "address": "123 Main St", "latitude": 40.7, "longitude": -74.0}
    ]


def test_search_restaurants_propagates_http_errors(monkeypatch):
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError("bad", request=MagicMock(), response=MagicMock())
    monkeypatch.setattr(places.httpx, "post", lambda *a, **k: response)

    with pytest.raises(httpx.HTTPStatusError):
        places.search_restaurants("Luigi's", None, None)


def test_nearby_restaurants_parses_sorts_and_skips_unnamed(monkeypatch):
    canned = {
        "elements": [
            {"type": "node", "id": 2, "lat": 40.720, "lon": -74.010,
             "tags": {"amenity": "restaurant", "name": "Far Place", "website": "https://far"}},
            {"type": "node", "id": 1, "lat": 40.7128, "lon": -74.0060,
             "tags": {"amenity": "restaurant", "name": "Near Place",
                      "addr:housenumber": "10", "addr:street": "Main St", "addr:city": "NYC"}},
            {"type": "way", "id": 5, "center": {"lat": 40.7130, "lon": -74.0062},
             "tags": {"amenity": "cafe", "name": "Way Cafe"}},
            # No name -> skipped, it cannot identify a restaurant.
            {"type": "node", "id": 9, "lat": 40.713, "lon": -74.006, "tags": {"amenity": "restaurant"}},
        ]
    }
    monkeypatch.setattr(places.httpx, "post", lambda *a, **k: _mock_response(canned))

    result = places.nearby_restaurants(40.7128, -74.0060)

    assert len(result) == 3
    assert result[0]["name"] == "Near Place"  # nearest-first
    near = result[0]
    assert near["restaurant_id"] == "osm-node-1"
    assert near["address"] == "10 Main St, NYC"
    assert near["distance_m"] <= result[-1]["distance_m"]
    assert result[0]["distance_m"] <= result[1]["distance_m"] <= result[2]["distance_m"]


def test_nearby_restaurants_raises_placeserror_on_http_error(monkeypatch):
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError("bad", request=MagicMock(), response=MagicMock())
    monkeypatch.setattr(places.httpx, "post", lambda *a, **k: response)

    with pytest.raises(places.PlacesError):
        places.nearby_restaurants(40.7, -74.0)


def test_nearby_restaurants_empty_when_no_elements(monkeypatch):
    monkeypatch.setattr(places.httpx, "post", lambda *a, **k: _mock_response({"elements": []}))

    assert places.nearby_restaurants(40.7, -74.0) == []
