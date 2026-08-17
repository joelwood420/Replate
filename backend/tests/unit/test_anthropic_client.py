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
