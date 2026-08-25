from unittest.mock import MagicMock

import httpx
import pytest

from shared import serpapi


def _mock_response(json_body: dict, status_ok: bool = True) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_body
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
    return response


def test_query_includes_name_and_address(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        return _mock_response({"organic_results": [{"link": "https://x.com"}]})

    monkeypatch.setattr(serpapi.httpx, "get", fake_get)

    serpapi.find_menu_url("Luigi's", "1 Main St", "key", 10)

    assert captured["url"] == serpapi.SERPAPI_URL
    assert captured["params"]["q"] == "Luigi's 1 Main St menu"
    assert captured["params"]["api_key"] == "key"
    assert captured["params"]["engine"] == "google"


def test_query_omits_address_when_absent(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        serpapi.httpx, "get",
        lambda url, params, headers, timeout: captured.update(params=params) or _mock_response({}),
    )

    serpapi.find_menu_url("Luigi's", None, "key", 10)

    assert captured["params"]["q"] == "Luigi's menu"


def test_prefers_a_knowledge_graph_menu_link(monkeypatch):
    body = {
        "knowledge_graph": {"menu": "https://luigis.com/the-menu"},
        "organic_results": [{"link": "https://elsewhere.com", "title": "Luigi's"}],
    }
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: _mock_response(body))

    assert serpapi.find_menu_url("Luigi's", None, "key", 10) == "https://luigis.com/the-menu"


def test_prefers_an_organic_result_that_reads_as_a_menu(monkeypatch):
    body = {
        "organic_results": [
            {"link": "https://luigis.com", "title": "Luigi's Restaurant"},
            {"link": "https://luigis.com/menu", "title": "Our Menu"},
        ]
    }
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: _mock_response(body))

    assert serpapi.find_menu_url("Luigi's", None, "key", 10) == "https://luigis.com/menu"


def test_prefers_an_aggregator_over_a_bare_homepage(monkeypatch):
    body = {
        "organic_results": [
            {"link": "https://luigis.com", "title": "Home"},
            {"link": "https://www.ubereats.com/store/luigis/abc", "title": "Luigi's on Uber Eats"},
        ]
    }
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: _mock_response(body))

    url = serpapi.find_menu_url("Luigi's", None, "key", 10)
    assert "ubereats.com" in url


def test_falls_back_to_the_top_organic_result(monkeypatch):
    body = {"organic_results": [{"link": "https://luigis.com", "title": "Home"}]}
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: _mock_response(body))

    assert serpapi.find_menu_url("Luigi's", None, "key", 10) == "https://luigis.com"


def test_returns_none_when_no_results(monkeypatch):
    monkeypatch.setattr(serpapi.httpx, "get", lambda *a, **k: _mock_response({"organic_results": []}))

    assert serpapi.find_menu_url("Luigi's", None, "key", 10) is None


def test_http_error_raises_serpapi_error(monkeypatch):
    monkeypatch.setattr(
        serpapi.httpx, "get", lambda *a, **k: _mock_response({}, status_ok=False)
    )

    with pytest.raises(serpapi.SerpApiError):
        serpapi.find_menu_url("Luigi's", None, "key", 10)


def test_a_logical_error_in_the_body_raises(monkeypatch):
    """SerpApi reports a bad key / exhausted quota as {'error': ...} with HTTP 200."""
    monkeypatch.setattr(
        serpapi.httpx, "get",
        lambda *a, **k: _mock_response({"error": "Your account has run out of searches."}),
    )

    with pytest.raises(serpapi.SerpApiError, match="run out of searches"):
        serpapi.find_menu_url("Luigi's", None, "key", 10)


def test_a_transport_error_raises_serpapi_error(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(serpapi.httpx, "get", boom)

    with pytest.raises(serpapi.SerpApiError):
        serpapi.find_menu_url("Luigi's", None, "key", 10)
