import httpx

from triggers import restaurant_search_http


def test_returns_400_when_query_missing():
    result = restaurant_search_http.run(None, None, None)

    assert result["status_code"] == 400
    assert "error" in result


def test_returns_400_when_query_blank():
    result = restaurant_search_http.run("   ", None, None)

    assert result["status_code"] == 400


def test_returns_502_when_places_raises(monkeypatch):
    def fake_search(*args, **kwargs):
        raise httpx.HTTPStatusError("bad", request=None, response=None)

    monkeypatch.setattr(restaurant_search_http.places, "search_restaurants", fake_search)

    result = restaurant_search_http.run("Luigi's", None, None)

    assert result["status_code"] == 502
    assert "error" in result


def test_returns_200_with_restaurants_on_success(monkeypatch):
    canned = [{"place_id": "p1", "name": "Luigi's", "address": "123 Main St", "latitude": 1.0, "longitude": 2.0}]
    monkeypatch.setattr(restaurant_search_http.places, "search_restaurants", lambda *a, **k: canned)

    result = restaurant_search_http.run("Luigi's", "40.7128", "-74.0060")

    assert result["status_code"] == 200
    assert result["restaurants"] == canned
