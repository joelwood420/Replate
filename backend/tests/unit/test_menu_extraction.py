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


def _patch_reformat(monkeypatch, outcome):
    """Stub the tool-free structured reformat pass that runs only when the web_search
    output was not clean JSON. Returns the recorded calls so a test can assert the
    reformat ran (and, crucially, that web_search did not run again)."""
    calls = []

    def fake_structured(model, messages, schema, system=None, **kwargs):
        calls.append({"model": model, "messages": messages, "system": system})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(anthropic_client, "generate_structured", fake_structured)
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


# --- reformat (no re-search) ------------------------------------------------


def test_unparseable_output_is_reformatted_without_searching_again(monkeypatch):
    """The costly bug was that a parse failure re-ran the whole web_search sweep.
    Now the model's own text is reshaped by a tool-free structured call, so
    web_search runs exactly once."""
    search_calls = _patch_model(monkeypatch, "here is the menu: not clean json")
    reformat_calls = _patch_reformat(
        monkeypatch,
        {"items": [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]},
    )

    items = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert items[0]["item_name"] == "Pad Thai"
    # web_search ran once; the retry was the cheap tool-free reformat, not a re-search.
    assert len(search_calls) == 1
    assert len(reformat_calls) == 1
    # The reformat is handed the raw web_search text to reshape.
    assert "not clean json" in reformat_calls[0]["messages"][0]["content"][0]["text"]


def test_reformat_normalizes_an_empty_price_to_none(monkeypatch):
    _patch_model(monkeypatch, "prose, not json")
    _patch_reformat(
        monkeypatch,
        {"items": [{"item_name": "Soup", "item_description": "", "price": ""}]},
    )

    item = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)[0]

    assert item["price"] is None


def test_a_failing_reformat_surfaces_as_a_menu_error(monkeypatch):
    """If even the tool-free reformat errors, degrade to a MenuExtractionError (the
    caller turns that into the vision-only outcome) - never a second web_search."""
    search_calls = _patch_model(monkeypatch, "prose, not json")
    _patch_reformat(monkeypatch, anthropic_client.AnthropicError("boom"))

    with pytest.raises(menu_extraction.MenuExtractionError, match="reformat"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert len(search_calls) == 1


def test_clean_json_never_triggers_a_reformat(monkeypatch):
    _patch_model(monkeypatch, VALID_JSON)
    reformat_calls = _patch_reformat(monkeypatch, {"items": []})

    menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert reformat_calls == []


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
