"""Menu extraction via the first-party Anthropic API's web_search tool.

One Claude call does search, fetch and extract (docs/decisions.md, 2026-08-17),
so there is no separate search/fetch seam to stub any more - these tests stub the
`anthropic_client.web_search_completion` call and check the extraction and its
retry behaviour, not the network. `parse_json_response` is left real so the
code-fence-stripping path is exercised end to end.
"""

import pytest

from shared import anthropic_client, menu_extraction

VALID_JSON = '{"items": [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]}'


@pytest.fixture(autouse=True)
def model_configured(monkeypatch):
    # A non-blank key makes anthropic_client.is_configured() true; a model id is set.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MENU_MODEL", "claude-test")


def _patch_model(monkeypatch, *responses):
    calls = []

    def fake_completion(model, messages, system=None, **kwargs):
        calls.append({"model": model, "messages": messages, "system": system})
        outcome = responses[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(anthropic_client, "web_search_completion", fake_completion)
    return calls


# --- happy path -------------------------------------------------------------


def test_parses_valid_json(monkeypatch):
    _patch_model(monkeypatch, VALID_JSON)

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", None)

    assert items == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]


def test_strips_a_markdown_code_fence(monkeypatch):
    _patch_model(monkeypatch, f"```json\n{VALID_JSON}\n```")

    assert menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)[0]["item_name"] == "Pad Thai"


def test_an_empty_menu_is_a_valid_answer(monkeypatch):
    """A restaurant with no findable menu should return nothing, not fail the job."""
    _patch_model(monkeypatch, '{"items": []}')

    assert menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None) == []


def test_a_missing_description_becomes_an_empty_string(monkeypatch):
    _patch_model(monkeypatch, '{"items": [{"item_name": "Pad Thai"}]}')

    item = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)[0]

    assert item["item_description"] == ""
    assert item["price"] is None


def test_the_restaurant_details_reach_the_prompt(monkeypatch):
    calls = _patch_model(monkeypatch, VALID_JSON)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", "https://example.com/menu")

    prompt = calls[0]["messages"][0]["content"][0]["text"]
    assert "Bangkok Kitchen" in prompt
    assert "1 Main St" in prompt
    assert "https://example.com/menu" in prompt


def test_the_configured_model_id_is_used(monkeypatch):
    calls = _patch_model(monkeypatch, VALID_JSON)

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert calls[0]["model"] == "claude-test"


# --- retries ----------------------------------------------------------------


def test_unparseable_output_is_retried_with_the_bad_output_shown(monkeypatch):
    """A blind retry tends to reproduce the same mistake, so the model is shown
    what it got wrong."""
    calls = _patch_model(monkeypatch, "not json at all", VALID_JSON)

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert items[0]["item_name"] == "Pad Thai"
    assert len(calls) == 2
    assert calls[1]["messages"][1]["content"][0]["text"] == "not json at all"


def test_gives_up_after_the_retry_budget(monkeypatch):
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "1")
    calls = _patch_model(monkeypatch, "nope", "still nope")

    with pytest.raises(menu_extraction.MenuExtractionError, match="after retries"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert len(calls) == 2


def test_an_item_without_a_name_is_rejected(monkeypatch):
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "0")
    _patch_model(monkeypatch, '{"items": [{"item_description": "no name"}]}')

    with pytest.raises(menu_extraction.MenuExtractionError):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_json_without_an_items_list_is_rejected(monkeypatch):
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "0")
    _patch_model(monkeypatch, '{"menu": []}')

    with pytest.raises(menu_extraction.MenuExtractionError):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


# --- failure surfaces -------------------------------------------------------


def test_an_anthropic_error_is_not_retried(monkeypatch):
    """A missing key or a key without model access will fail identically every time."""
    monkeypatch.setenv("MENU_FETCH_MAX_RETRIES", "3")
    calls = _patch_model(monkeypatch, anthropic_client.AnthropicError("AuthenticationError"))

    with pytest.raises(menu_extraction.MenuExtractionError, match="Anthropic error"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert len(calls) == 1


def test_a_missing_key_degrades_rather_than_crashing(monkeypatch):
    """The caller's graceful degrade turns this into the vision-only medium-confidence
    outcome, so it must be a MenuExtractionError, not a raw crash."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="ANTHROPIC_API_KEY"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_a_missing_model_id_degrades_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MENU_MODEL", "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="ANTHROPIC_MENU_MODEL"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)
