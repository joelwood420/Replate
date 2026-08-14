"""Search and page-fetch - the two stages that replaced Anthropic's web_search tool."""

import httpx
import pytest

from shared import web_search


@pytest.fixture(autouse=True)
def serp_configured(monkeypatch):
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_MAX_RESULTS", "3")


def _patch_get(monkeypatch, *outcomes):
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(web_search.httpx, "get", fake_get)
    return calls


def _response(status=200, json_body=None, text=""):
    request = httpx.Request("GET", "https://example.com")
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=request)
    return httpx.Response(status, text=text, request=request)


# --- search -----------------------------------------------------------------


def test_parses_brave_style_results(monkeypatch):
    _patch_get(
        monkeypatch,
        _response(json_body={"web": {"results": [{"title": "Menu", "url": "https://a/menu"}]}}),
    )

    assert web_search.search("thai menu") == [{"title": "Menu", "url": "https://a/menu"}]


@pytest.mark.parametrize("key", ["organic_results", "results"])
def test_parses_other_common_result_shapes(monkeypatch, key):
    """Swapping SERP provider should be a config change, not a rewrite."""
    _patch_get(monkeypatch, _response(json_body={key: [{"title": "M", "link": "https://a/m"}]}))

    assert web_search.search("thai menu")[0]["url"] == "https://a/m"


def test_an_unrecognised_shape_yields_no_results(monkeypatch):
    _patch_get(monkeypatch, _response(json_body={"something": "else"}))

    assert web_search.search("thai menu") == []


def test_results_are_capped(monkeypatch):
    monkeypatch.setenv("SERP_MAX_RESULTS", "2")
    _patch_get(
        monkeypatch,
        _response(
            json_body={"web": {"results": [{"url": f"https://a/{i}"} for i in range(5)]}}
        ),
    )

    assert len(web_search.search("thai menu")) == 2


def test_an_unconfigured_key_raises_search_error(monkeypatch):
    monkeypatch.setenv("SERP_API_KEY", "")

    with pytest.raises(web_search.SearchError, match="SERP_API_KEY"):
        web_search.search("thai menu")


def test_an_http_error_becomes_a_search_error(monkeypatch):
    _patch_get(monkeypatch, httpx.ConnectError("boom"))

    with pytest.raises(web_search.SearchError):
        web_search.search("thai menu")


def test_a_4xx_becomes_a_search_error(monkeypatch):
    _patch_get(monkeypatch, _response(status=401, text="unauthorized"))

    with pytest.raises(web_search.SearchError, match="401"):
        web_search.search("thai menu")


# --- html to text -----------------------------------------------------------


def test_scripts_and_styles_are_removed_not_just_untagged():
    """Their contents are not markup, so tag-stripping alone leaves them as noise."""
    markup = "<html><script>var x = 1;</script><style>.a{color:red}</style><p>Pad Thai</p></html>"

    text = web_search.html_to_text(markup)

    assert "var x" not in text
    assert "color:red" not in text
    assert "Pad Thai" in text


def test_entities_are_unescaped():
    assert "Fish & Chips" in web_search.html_to_text("<p>Fish &amp; Chips</p>")


def test_runs_of_blank_lines_are_collapsed():
    text = web_search.html_to_text("<div></div><div></div><div></div><p>Item</p>")

    assert "\n\n\n" not in text


# --- page fetch -------------------------------------------------------------


def test_fetch_returns_visible_text(monkeypatch):
    _patch_get(monkeypatch, _response(text="<html><body><p>Pad Thai 13.00</p></body></html>"))

    assert web_search.fetch_page_text("https://a/menu") == "Pad Thai 13.00"


def test_fetch_truncates_to_the_budget(monkeypatch):
    """Unbounded page text goes straight into a model prompt - this is a cost cap,
    not a nicety."""
    monkeypatch.setenv("PAGE_FETCH_MAX_CHARS", "20")
    _patch_get(monkeypatch, _response(text="<p>" + "x" * 500 + "</p>"))

    assert len(web_search.fetch_page_text("https://a/menu")) == 20


def test_fetch_follows_redirects(monkeypatch):
    calls = _patch_get(monkeypatch, _response(text="<p>ok</p>"))

    web_search.fetch_page_text("https://a/menu")

    assert calls[0]["follow_redirects"] is True


def test_a_404_becomes_a_search_error(monkeypatch):
    _patch_get(monkeypatch, _response(status=404, text="gone"))

    with pytest.raises(web_search.SearchError, match="404"):
        web_search.fetch_page_text("https://a/menu")


# --- find_menu_page ---------------------------------------------------------


def test_a_known_url_skips_the_search(monkeypatch):
    """One fewer billable call, and a known-good URL beats a search result."""
    calls = _patch_get(monkeypatch, _response(text="<p>Pad Thai</p>"))

    url, text = web_search.find_menu_page("Bangkok Kitchen", None, "https://known/menu")

    assert url == "https://known/menu"
    assert text == "Pad Thai"
    assert len(calls) == 1


def test_a_stale_known_url_falls_back_to_search(monkeypatch):
    """A cached URL that has rotted must not permanently break menu fetching."""
    _patch_get(
        monkeypatch,
        _response(status=404, text="gone"),
        _response(json_body={"web": {"results": [{"url": "https://found/menu"}]}}),
        _response(text="<p>Pad Thai</p>"),
    )

    url, _ = web_search.find_menu_page("Bangkok Kitchen", None, "https://stale/menu")

    assert url == "https://found/menu"


def test_the_search_query_includes_the_address(monkeypatch):
    calls = _patch_get(
        monkeypatch,
        _response(json_body={"web": {"results": [{"url": "https://a/m"}]}}),
        _response(text="<p>x</p>"),
    )

    web_search.find_menu_page("Bangkok Kitchen", "1 Main St", None)

    assert calls[0]["params"]["q"] == "Bangkok Kitchen 1 Main St menu"


def test_a_failing_result_falls_through_to_the_next(monkeypatch):
    _patch_get(
        monkeypatch,
        _response(json_body={"web": {"results": [{"url": "https://a/1"}, {"url": "https://a/2"}]}}),
        _response(status=500, text="oops"),
        _response(text="<p>Pad Thai</p>"),
    )

    url, _ = web_search.find_menu_page("Bangkok Kitchen", None, None)

    assert url == "https://a/2"


def test_no_results_raises(monkeypatch):
    _patch_get(monkeypatch, _response(json_body={"web": {"results": []}}))

    with pytest.raises(web_search.SearchError, match="no search results"):
        web_search.find_menu_page("Bangkok Kitchen", None, None)


def test_every_candidate_failing_raises(monkeypatch):
    _patch_get(
        monkeypatch,
        _response(json_body={"web": {"results": [{"url": "https://a/1"}]}}),
        _response(status=500, text="oops"),
    )

    with pytest.raises(web_search.SearchError, match="every candidate page failed"):
        web_search.find_menu_page("Bangkok Kitchen", None, None)
