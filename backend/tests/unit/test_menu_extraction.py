"""Menu extraction via the deterministic SerpApi + page-fetch + structured-extract pipeline.

These stub the three seams - `serpapi.find_menu_url`, `page_fetch.fetch_menu_content` and
`anthropic_client.generate_structured` - and check the orchestration, budgeting and content-
block construction, not the network. `_validate` is left real.
"""

import pytest

from shared import anthropic_client, menu_extraction, page_fetch, serpapi

EXTRACTED = {"items": [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    # A non-blank Anthropic key makes is_configured() true; a menu model + SerpApi key are set.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MENU_MODEL", "claude-test")
    monkeypatch.setenv("SERPAPI_KEY", "serp-test")
    monkeypatch.setenv("SERPAPI_KEY_PARAM", "")


def _patch_url(monkeypatch, outcome):
    """Stub SerpApi discovery. `outcome` is a URL, None, or a SerpApiError to raise."""
    calls = []

    def fake(name, address, api_key, timeout):
        calls.append({"name": name, "address": address, "api_key": api_key})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(serpapi, "find_menu_url", fake)
    return calls


def _patch_fetch(monkeypatch, outcome):
    calls = []

    def fake(url, timeout):
        calls.append(url)
        return outcome

    monkeypatch.setattr(page_fetch, "fetch_menu_content", fake)
    return calls


def _patch_extract(monkeypatch, outcome):
    calls = []

    def fake(model, messages, schema, system=None, **kwargs):
        calls.append({"model": model, "messages": messages, "system": system, "kwargs": kwargs})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(anthropic_client, "generate_structured", fake)
    return calls


def _patch_fetch_map(monkeypatch, mapping):
    """Stub page_fetch by URL substring. Values are content dicts, None, or an Exception."""
    calls = []

    def fake(url, timeout):
        calls.append(url)
        for key, value in mapping.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        return None

    monkeypatch.setattr(page_fetch, "fetch_menu_content", fake)
    return calls


def _patch_extract_seq(monkeypatch, *outcomes):
    """Stub generate_structured with a per-call sequence (last outcome repeats if exhausted)."""
    calls = []

    def fake(model, messages, schema, system=None, **kwargs):
        outcome = outcomes[len(calls)] if len(calls) < len(outcomes) else outcomes[-1]
        calls.append({"messages": messages, "kwargs": kwargs})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(anthropic_client, "generate_structured", fake)
    return calls


def _item(name):
    return {"item_name": name, "item_description": "d", "price": "1"}


# --- happy paths ------------------------------------------------------------


def test_html_menu_is_extracted(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu")
    fetch_calls = _patch_fetch(monkeypatch, {"kind": "html", "text": "Pad Thai 13.00"})
    extract_calls = _patch_extract(monkeypatch, EXTRACTED)

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", None)

    assert items == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    assert fetch_calls == ["https://x.com/menu"]
    # The stripped page text reaches the model as a plain text block.
    content = extract_calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert "Pad Thai 13.00" in content[0]["text"]


def test_pdf_menu_becomes_a_document_block(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu.pdf")
    _patch_fetch(monkeypatch, {"kind": "pdf", "data": b"%PDF-1.4 ...", "media_type": "application/pdf"})
    extract_calls = _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    content = extract_calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "document"
    assert content[0]["source"]["media_type"] == "application/pdf"
    assert content[0]["source"]["type"] == "base64"
    # The instruction text follows the document block.
    assert content[1]["type"] == "text"


def test_image_menu_becomes_an_image_block(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu.jpg")
    _patch_fetch(monkeypatch, {"kind": "image", "data": b"\xff\xd8\xff", "media_type": "image/jpeg"})
    extract_calls = _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    content = extract_calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/jpeg"


def test_the_configured_model_id_is_used(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu")
    _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    extract_calls = _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert extract_calls[0]["model"] == "claude-test"


def test_the_extract_call_is_bounded_by_the_remaining_budget(monkeypatch):
    """A slow extract must fail inside the budget, not run until the Lambda is killed."""
    monkeypatch.setenv("MENU_FETCH_BUDGET_SECONDS", "45")
    _patch_url(monkeypatch, "https://x.com/menu")
    _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    extract_calls = _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    timeout = extract_calls[0]["kwargs"]["timeout"]
    assert 0 < timeout <= 45


def test_a_missing_description_and_price_normalize(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu")
    _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    _patch_extract(monkeypatch, {"items": [{"item_name": "Soup", "item_description": "", "price": ""}]})

    item = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)[0]

    assert item["item_description"] == ""
    assert item["price"] is None


# --- URL discovery + fallback ----------------------------------------------


def test_serpapi_gets_the_name_and_address(monkeypatch):
    url_calls = _patch_url(monkeypatch, "https://x.com/menu")
    _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", None)

    assert url_calls[0]["name"] == "Bangkok Kitchen"
    assert url_calls[0]["address"] == "1 Main St"


def test_falls_back_to_the_osm_url_when_serpapi_finds_nothing(monkeypatch):
    _patch_url(monkeypatch, None)
    fetch_calls = _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, "https://osm-hint.com/menu")

    assert fetch_calls == ["https://osm-hint.com/menu"]


def test_serpapi_error_with_an_osm_url_still_extracts(monkeypatch):
    _patch_url(monkeypatch, serpapi.SerpApiError("quota"))
    fetch_calls = _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    _patch_extract(monkeypatch, EXTRACTED)

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, "https://osm-hint.com/menu")

    assert items == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    assert fetch_calls == ["https://osm-hint.com/menu"]


def test_no_url_at_all_is_a_cacheable_empty_result(monkeypatch):
    """A clean search with no URL and no OSM hint is 'no menu online' - an empty list, which
    the activity caches, not an error."""
    _patch_url(monkeypatch, None)

    assert menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None) == []


def test_serpapi_error_with_no_fallback_url_raises(monkeypatch):
    """A transient SerpApi failure with nothing to fall back to must NOT cache an empty menu,
    so it raises - the caller degrades and the next job retries."""
    _patch_url(monkeypatch, serpapi.SerpApiError("boom"))

    with pytest.raises(menu_extraction.MenuExtractionError, match="Could not discover a menu URL"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_no_serpapi_key_and_no_url_raises(monkeypatch):
    """A missing SerpApi key with no OSM fallback is a config gap, not 'no menu' - raise so it
    is retried once the key lands, rather than caching the restaurant as menu-less."""
    monkeypatch.setenv("SERPAPI_KEY", "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="Could not discover a menu URL"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_a_page_fetch_transport_error_raises_and_is_not_cached(monkeypatch):
    """A one-off network blip fetching the page must not cache a permanent no-menu."""
    _patch_url(monkeypatch, "https://x.com/menu")

    def boom(url, timeout):
        raise page_fetch.PageFetchError("no route")

    monkeypatch.setattr(page_fetch, "fetch_menu_content", boom)

    with pytest.raises(menu_extraction.MenuExtractionError, match="Menu page fetch failed"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_no_serpapi_key_uses_the_osm_url(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "")
    # find_menu_url must not be called without a key.
    monkeypatch.setattr(
        serpapi, "find_menu_url", lambda *a, **k: pytest.fail("should not call SerpApi without a key")
    )
    fetch_calls = _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    _patch_extract(monkeypatch, EXTRACTED)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, "https://osm-hint.com/menu")

    assert fetch_calls == ["https://osm-hint.com/menu"]


# --- fetch outcomes ---------------------------------------------------------


def test_a_url_yielding_no_content_is_a_cacheable_empty_result(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu")
    _patch_fetch(monkeypatch, None)
    _patch_extract(monkeypatch, {"items": []})  # should never be reached

    assert menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None) == []


# --- following linked PDF menus ---------------------------------------------


def test_follows_a_linked_pdf_menu(monkeypatch):
    """An HTML menu page that only links to PDF menus: follow the PDF and extract from it."""
    _patch_url(monkeypatch, "https://x.com/menus")
    _patch_fetch_map(
        monkeypatch,
        {
            "menus": {"kind": "html", "text": "nav and marketing only", "pdf_links": ["https://x.com/food.pdf"]},
            "food.pdf": {"kind": "pdf", "data": b"%PDF", "media_type": "application/pdf"},
        },
    )
    extract_calls = _patch_extract_seq(monkeypatch, EXTRACTED)

    items = menu_extraction.fetch_menu_items("Baduzzi", None, None)

    assert items == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    # One extract, on the PDF (a document block) - the empty HTML text is never extracted.
    assert len(extract_calls) == 1
    assert extract_calls[0]["messages"][0]["content"][0]["type"] == "document"


def test_falls_back_to_html_when_the_pdf_yields_nothing(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menus")
    _patch_fetch_map(
        monkeypatch,
        {
            "menus": {"kind": "html", "text": "Pad Thai on the page", "pdf_links": ["https://x.com/food.pdf"]},
            "food.pdf": {"kind": "pdf", "data": b"%PDF", "media_type": "application/pdf"},
        },
    )
    # PDF extract empty, then the HTML text extract finds items.
    extract_calls = _patch_extract_seq(monkeypatch, {"items": []}, EXTRACTED)

    items = menu_extraction.fetch_menu_items("Baduzzi", None, None)

    assert items[0]["item_name"] == "Pad Thai"
    assert len(extract_calls) == 2
    assert extract_calls[1]["messages"][0]["content"][0]["type"] == "text"


def test_merges_and_dedups_across_followed_pdfs(monkeypatch):
    monkeypatch.setenv("MENU_PDF_MAX_FOLLOW", "2")
    _patch_url(monkeypatch, "https://x.com/menus")
    _patch_fetch_map(
        monkeypatch,
        {
            "menus": {"kind": "html", "text": "nav", "pdf_links": ["https://x.com/a.pdf", "https://x.com/b.pdf"]},
            "a.pdf": {"kind": "pdf", "data": b"%PDF", "media_type": "application/pdf"},
            "b.pdf": {"kind": "pdf", "data": b"%PDF", "media_type": "application/pdf"},
        },
    )
    _patch_extract_seq(
        monkeypatch,
        {"items": [_item("Pad Thai"), _item("Soup")]},
        {"items": [_item("pad thai"), _item("Curry")]},  # "pad thai" duplicates across PDFs
    )

    items = menu_extraction.fetch_menu_items("Baduzzi", None, None)

    assert [i["item_name"] for i in items] == ["Pad Thai", "Soup", "Curry"]


def test_respects_the_pdf_follow_cap(monkeypatch):
    monkeypatch.setenv("MENU_PDF_MAX_FOLLOW", "1")
    _patch_url(monkeypatch, "https://x.com/menus")
    _patch_fetch_map(
        monkeypatch,
        {
            "menus": {"kind": "html", "text": "nav", "pdf_links": ["https://x.com/a.pdf", "https://x.com/b.pdf"]},
            "a.pdf": {"kind": "pdf", "data": b"%PDF", "media_type": "application/pdf"},
            "b.pdf": {"kind": "pdf", "data": b"%PDF", "media_type": "application/pdf"},
        },
    )
    extract_calls = _patch_extract_seq(monkeypatch, {"items": [_item("A")]})

    items = menu_extraction.fetch_menu_items("Baduzzi", None, None)

    assert len(extract_calls) == 1  # only the first PDF was followed
    assert [i["item_name"] for i in items] == ["A"]


# --- budget -----------------------------------------------------------------


def test_budget_exhausted_before_fetch_raises(monkeypatch):
    monkeypatch.setenv("MENU_FETCH_BUDGET_SECONDS", "0")
    _patch_url(monkeypatch, "https://x.com/menu")

    with pytest.raises(menu_extraction.MenuExtractionError, match="budget"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


# --- extract failure surfaces ----------------------------------------------


def test_an_anthropic_error_surfaces_as_a_menu_error(monkeypatch):
    _patch_url(monkeypatch, "https://x.com/menu")
    _patch_fetch(monkeypatch, {"kind": "html", "text": "items"})
    _patch_extract(monkeypatch, anthropic_client.AnthropicError("AuthenticationError"))

    with pytest.raises(menu_extraction.MenuExtractionError, match="Anthropic error"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_a_missing_key_degrades_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="ANTHROPIC_API_KEY"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_a_missing_model_id_degrades_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MENU_MODEL", "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="ANTHROPIC_MENU_MODEL"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)
