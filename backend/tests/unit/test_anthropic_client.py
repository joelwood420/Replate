"""Anthropic API key resolution and SSM SecureString caching.

Deployed, the key comes from SSM Parameter Store (ANTHROPIC_API_KEY_PARAM);
locally / in tests it comes from the ANTHROPIC_API_KEY env var. A failed SSM read
degrades to the no-key path so menu fetch falls back to the vision-only outcome
rather than crashing.
"""

import pytest

from shared import anthropic_client, secrets


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    secrets.reset_caches()
    anthropic_client.reset_client_cache()
    # Start from a clean slate: neither source configured unless a test sets it.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY_PARAM", raising=False)
    yield
    secrets.reset_caches()


# --- key resolution ---------------------------------------------------------


def test_env_var_is_used_when_no_param_is_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")

    assert anthropic_client.is_configured() is True
    assert anthropic_client._resolved_key() == "sk-ant-env"


def test_no_key_anywhere_is_not_configured():
    assert anthropic_client.is_configured() is False
    assert anthropic_client._resolved_key() == ""


def test_ssm_param_is_read_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY_PARAM", "/replate/anthropic-api-key")
    monkeypatch.setattr(
        secrets, "get_secure_parameter", lambda name: "sk-ant-from-ssm"
    )

    assert anthropic_client.is_configured() is True
    assert anthropic_client._resolved_key() == "sk-ant-from-ssm"


def test_ssm_param_takes_precedence_over_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    monkeypatch.setenv("ANTHROPIC_API_KEY_PARAM", "/replate/anthropic-api-key")
    monkeypatch.setattr(secrets, "get_secure_parameter", lambda name: "sk-ant-ssm")

    assert anthropic_client._resolved_key() == "sk-ant-ssm"


def test_ssm_failure_degrades_to_the_no_key_path(monkeypatch):
    """A missing parameter or denied read must not crash - it becomes the vision-only
    outcome, the same as a blank key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY_PARAM", "/replate/anthropic-api-key")

    def boom(name):
        raise RuntimeError("ParameterNotFound")

    monkeypatch.setattr(secrets, "get_secure_parameter", boom)

    assert anthropic_client.is_configured() is False
    assert anthropic_client._resolved_key() == ""


# --- SSM caching ------------------------------------------------------------


def test_secure_parameter_is_cached_after_the_first_read(monkeypatch):
    calls = []

    class FakeSsm:
        def get_parameter(self, Name, WithDecryption):
            calls.append((Name, WithDecryption))
            return {"Parameter": {"Value": "secret-value"}}

    monkeypatch.setattr(secrets, "get_client", lambda: FakeSsm())

    assert secrets.get_secure_parameter("/replate/anthropic-api-key") == "secret-value"
    assert secrets.get_secure_parameter("/replate/anthropic-api-key") == "secret-value"

    # One decrypt call for two reads - the value is cached per Lambda container.
    assert calls == [("/replate/anthropic-api-key", True)]


def test_a_failed_read_is_not_cached(monkeypatch):
    attempts = []

    class FlakySsm:
        def get_parameter(self, Name, WithDecryption):
            attempts.append(Name)
            if len(attempts) == 1:
                raise RuntimeError("transient")
            return {"Parameter": {"Value": "eventual-value"}}

    monkeypatch.setattr(secrets, "get_client", lambda: FlakySsm())

    with pytest.raises(RuntimeError):
        secrets.get_secure_parameter("/replate/anthropic-api-key")

    # The transient failure was not cached, so a second call retries and succeeds.
    assert secrets.get_secure_parameter("/replate/anthropic-api-key") == "eventual-value"
    assert len(attempts) == 2


# --- web_search wall-clock budget -------------------------------------------
# A slow or looping menu web_search must fail here (as an AnthropicError the caller
# degrades to vision-only) rather than run until the Lambda is killed and the whole
# scan is marked Failed - the 2026-08-24 Sandbox.Timedout incident.


class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5
    server_tool_use = None


class _FakeResponse:
    def __init__(self, text="", stop_reason="end_turn"):
        self.content = [_FakeBlock(text)] if text else []
        self.stop_reason = stop_reason
        self.usage = _FakeUsage()


class _FakeClient:
    """Stands in for the Anthropic SDK client: with_options().messages.create()."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.create_calls = 0

    def with_options(self, **_kwargs):
        return self

    @property
    def messages(self):
        return self

    def create(self, **_kwargs):
        response = self._responses[min(self.create_calls, len(self._responses) - 1)]
        self.create_calls += 1
        return response


def _msgs():
    return [{"role": "user", "content": [{"type": "text", "text": "find the menu"}]}]


def test_web_search_returns_text_on_a_normal_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    fake = _FakeClient([_FakeResponse("menu json", "end_turn")])
    monkeypatch.setattr(anthropic_client, "get_client", lambda: fake)

    out = anthropic_client.web_search_completion("claude-test", _msgs())

    assert out == "menu json"
    assert fake.create_calls == 1


def test_web_search_gives_up_when_the_budget_is_exhausted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(anthropic_client.app_config, "web_search_timeout_seconds", lambda: 10.0)
    # First reading sets the deadline (t0=1000 -> deadline 1010); the next leaves only 5s,
    # below _MIN_RESUME_SECONDS, so the paused turn is not resumed.
    times = iter([1000.0, 1005.0])
    monkeypatch.setattr(anthropic_client.time, "monotonic", lambda: next(times))
    fake = _FakeClient([_FakeResponse("", "pause_turn")])
    monkeypatch.setattr(anthropic_client, "get_client", lambda: fake)

    with pytest.raises(anthropic_client.AnthropicError, match="budget"):
        anthropic_client.web_search_completion("claude-test", _msgs())

    assert fake.create_calls == 1  # initial call only; no resume attempted


def test_web_search_stops_after_the_resume_cap(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(anthropic_client.app_config, "web_search_timeout_seconds", lambda: 1000.0)
    monkeypatch.setattr(anthropic_client.time, "monotonic", lambda: 0.0)  # budget never runs down
    fake = _FakeClient(
        [
            _FakeResponse("", "pause_turn"),
            _FakeResponse("", "pause_turn"),
            _FakeResponse("final menu", "pause_turn"),
        ]
    )
    monkeypatch.setattr(anthropic_client, "get_client", lambda: fake)

    out = anthropic_client.web_search_completion("claude-test", _msgs())

    assert out == "final menu"
    # initial + _MAX_PAUSE_RESUMES resumes, then it stops even though still paused.
    assert fake.create_calls == 1 + anthropic_client._MAX_PAUSE_RESUMES


# --- structured output: truncated or malformed replies -----------------------
# A reply cut off at max_tokens used to escape as a bare JSONDecodeError, which
# callers don't catch, so a large menu failed the whole scan instead of degrading
# to vision-only (Baduzzi, 2026-10-01).


def test_structured_reply_hitting_max_tokens_is_an_anthropic_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    fake = _FakeClient([_FakeResponse('{"items": [{"name": "Tart', "max_tokens")])
    monkeypatch.setattr(anthropic_client, "get_client", lambda: fake)

    with pytest.raises(anthropic_client.AnthropicError, match="max_tokens"):
        anthropic_client.generate_structured("claude-test", _msgs(), schema={})


def test_structured_reply_with_invalid_json_is_an_anthropic_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    fake = _FakeClient([_FakeResponse('{"items": [} oops', "end_turn")])
    monkeypatch.setattr(anthropic_client, "get_client", lambda: fake)

    with pytest.raises(anthropic_client.AnthropicError, match="invalid JSON"):
        anthropic_client.generate_structured("claude-test", _msgs(), schema={})


def test_structured_reply_parses_valid_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    fake = _FakeClient([_FakeResponse('{"items": []}', "end_turn")])
    monkeypatch.setattr(anthropic_client, "get_client", lambda: fake)

    assert anthropic_client.generate_structured("claude-test", _msgs(), schema={}) == {"items": []}
