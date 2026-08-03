import pytest

from shared import menu_extraction


class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeResponse:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.content = [_TextBlock(text)]
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.messages = _FakeMessages(responses)


def _patch_client(monkeypatch, responses):
    fake_client = _FakeClient(responses)
    monkeypatch.setattr(menu_extraction, "Anthropic", lambda **kwargs: fake_client)
    # Stub the key too: fetch_menu_items now fails fast on a blank one, and the local
    # .env legitimately leaves ANTHROPIC_API_KEY empty. These tests cover extraction
    # logic, not auth config - see test_missing_api_key_raises_menu_extraction_error.
    monkeypatch.setattr(menu_extraction.config, "anthropic_api_key", lambda: "sk-test-key")
    return fake_client


VALID_JSON = '{"items": [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]}'


def test_valid_json_happy_path(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(VALID_JSON)])

    result = menu_extraction.fetch_menu_items("Bangkok Kitchen", "1 Main St", None)

    assert result == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]


def test_invalid_json_then_valid_on_retry(monkeypatch):
    fake_client = _patch_client(monkeypatch, [_FakeResponse("not json"), _FakeResponse(VALID_JSON)])

    result = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert result == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    assert len(fake_client.messages.calls) == 2


def test_pause_turn_resumes_with_prior_assistant_turn(monkeypatch):
    paused_response = _FakeResponse("(paused mid-search)", stop_reason="pause_turn")
    fake_client = _patch_client(monkeypatch, [paused_response, _FakeResponse(VALID_JSON)])

    result = menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)

    assert result == [{"item_name": "Pad Thai", "item_description": "desc", "price": "13.00"}]
    # Resume must re-send exactly [user(prompt), assistant(paused content)] - no
    # synthetic "continue" message appended.
    second_call_messages = fake_client.messages.calls[1]["messages"]
    assert len(second_call_messages) == 2
    assert second_call_messages[0]["role"] == "user"
    assert second_call_messages[1] == {"role": "assistant", "content": paused_response.content}


def test_exhausted_retries_raises_menu_extraction_error(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse("not json")] * 10)

    with pytest.raises(menu_extraction.MenuExtractionError):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)


def test_missing_api_key_raises_menu_extraction_error(monkeypatch):
    """A blank key must surface as MenuExtractionError, not a bare TypeError.

    fetch_restaurant_menu only catches MenuExtractionError in order to degrade to an
    empty menu instead of failing the whole job. Anthropic(api_key="") raises TypeError
    from the SDK constructor, which would escape that path.
    """
    monkeypatch.setattr(menu_extraction.config, "anthropic_api_key", lambda: "")

    with pytest.raises(menu_extraction.MenuExtractionError, match="ANTHROPIC_API_KEY"):
        menu_extraction.fetch_menu_items("Bangkok Kitchen", None, None)
