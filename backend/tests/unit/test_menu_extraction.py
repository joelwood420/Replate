"""Menu extraction after the search -> fetch -> extract split.

Was one Claude call with a server-side web_search tool; Bedrock does not expose
that tool, so the search and fetch stages moved into shared/web_search.py and
this module only structures page text. These tests stub both seams - what is
being checked is the extraction and its retry behaviour, not the network.
"""

import pytest

from shared import bedrock, menu_extraction, web_search

VALID_JSON = '{"items": [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]}'


@pytest.fixture(autouse=True)
def model_configured(monkeypatch):
    monkeypatch.setenv("BEDROCK_MENU_MODEL_ID", "anthropic.claude-haiku-test")


@pytest.fixture
def page(monkeypatch):
    """Stub the search + fetch half so only extraction is under test."""
    monkeypatch.setattr(
        menu_extraction.web_search,
        "find_menu_page",
        lambda name, address, url: ("https://example.com/menu", "Pad Thai 13.00"),
    )


def _patch_model(monkeypatch, *responses):
    calls = []

    def fake_converse(model_id, messages, system=None, **kwargs):
        calls.append({"model_id": model_id, "messages": messages, "system": system})
        outcome = responses[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(menu_extraction.bedrock, "converse", fake_converse)
    return calls


# --- happy path -------------------------------------------------------------


def test_parses_valid_json(monkeypatch, page):
    _patch_model(monkeypatch, VALID_JSON)

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", None)

    assert items == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]


def test_strips_a_markdown_code_fence(monkeypatch, page):
    _patch_model(monkeypatch, f"```json\n{VALID_JSON}\n```")

    assert menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)[0]["item_name"] == "Pad Thai"


def test_an_empty_menu_is_a_valid_answer(monkeypatch, page):
    """A page that is not a menu should return nothing, not fail the job."""
    _patch_model(monkeypatch, '{"items": []}')

    assert menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None) == []


def test_a_missing_description_becomes_an_empty_string(monkeypatch, page):
    _patch_model(monkeypatch, '{"items": [{"item_name": "Pad Thai"}]}')

    item = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)[0]

    assert item["item_description"] == ""
    assert item["price"] is None


def test_the_page_url_and_text_reach_the_prompt(monkeypatch, page):
    calls = _patch_model(monkeypatch, VALID_JSON)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", None)

    prompt = calls[0]["messages"][0]["content"][0]["text"]
    assert "https://example.com/menu" in prompt
    assert "Pad Thai 13.00" in prompt
    assert "1 Main St" in prompt


def test_the_configured_model_id_is_used(monkeypatch, page):
    calls = _patch_model(monkeypatch, VALID_JSON)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert calls[0]["model_id"] == "anthropic.claude-haiku-test"


# --- retries ----------------------------------------------------------------


def test_unparseable_output_is_retried_with_the_bad_output_shown(monkeypatch, page):
    """A blind retry at temperature 0 tends to reproduce the same mistake, so the
    model is shown what it got wrong."""
    calls = _patch_model(monkeypatch, "not json at all", VALID_JSON)

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert items[0]["item_name"] == "Pad Thai"
    assert len(calls) == 2
    assert calls[1]["messages"][1]["content"][0]["text"] == "not json at all"


def test_gives_up_after_the_retry_budget(monkeypatch, page):
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "1")
    calls = _patch_model(monkeypatch, "nope", "still nope")

    with pytest.raises(menu_extraction.MenuExtractionError, match="after retries"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert len(calls) == 2


def test_an_item_without_a_name_is_rejected(monkeypatch, page):
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "0")
    _patch_model(monkeypatch, '{"items": [{"item_description": "no name"}]}')

    with pytest.raises(menu_extraction.MenuExtractionError):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_json_without_an_items_list_is_rejected(monkeypatch, page):
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "0")
    _patch_model(monkeypatch, '{"menu": []}')

    with pytest.raises(menu_extraction.MenuExtractionError):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


# --- failure surfaces -------------------------------------------------------


def test_a_bedrock_error_is_not_retried(monkeypatch, page):
    """A missing model id or an ungranted model will fail identically every time."""
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "3")
    calls = _patch_model(monkeypatch, bedrock.BedrockError("AccessDeniedException"))

    with pytest.raises(menu_extraction.MenuExtractionError, match="Bedrock error"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert len(calls) == 1


def test_a_missing_model_id_degrades_rather_than_crashing(monkeypatch):
    """Same contract the missing-ANTHROPIC_API_KEY path had: the caller's graceful
    degrade turns this into the vision-only medium-confidence outcome."""
    monkeypatch.setenv("BEDROCK_MENU_MODEL_ID", "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="BEDROCK_MENU_MODEL_ID"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_a_search_failure_becomes_a_menu_extraction_error(monkeypatch):
    def explode(name, address, url):
        raise web_search.SearchError("no results")

    monkeypatch.setattr(menu_extraction.web_search, "find_menu_page", explode)

    with pytest.raises(menu_extraction.MenuExtractionError, match="Could not find a menu page"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_a_blank_page_is_rejected_before_calling_the_model(monkeypatch):
    """Paying for a model call on an empty page is pure waste."""
    monkeypatch.setattr(
        menu_extraction.web_search, "find_menu_page", lambda *a: ("https://x", "   \n  ")
    )

    def explode(*args, **kwargs):
        raise AssertionError("must not call the model for an empty page")

    monkeypatch.setattr(menu_extraction.bedrock, "converse", explode)

    with pytest.raises(menu_extraction.MenuExtractionError, match="no readable text"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)
