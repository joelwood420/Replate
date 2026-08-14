import pytest

from shared import auth


def _event(headers=None):
    return {"headers": headers or {}, "requestContext": {"http": {"method": "POST", "path": "/jobs"}}}


def test_stub_mode_uses_header_and_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(auth.config, "cognito_enabled", lambda: False)

    assert auth.get_user_oid(_event({"X-Debug-User-Oid": "explicit-oid"})) == "explicit-oid"
    assert auth.get_user_oid(_event()) == auth.config.stub_default_user_oid()


def test_header_lookup_is_case_insensitive(monkeypatch):
    """API Gateway lower-cases header names in payload format 2.0, but not every
    local emulator does - so the lookup must not depend on the casing."""
    monkeypatch.setattr(auth.config, "cognito_enabled", lambda: False)

    assert auth.get_user_oid(_event({"x-debug-user-oid": "lowercased"})) == "lowercased"


def test_cognito_enabled_raises_not_implemented(monkeypatch):
    monkeypatch.setattr(auth.config, "cognito_enabled", lambda: True)

    with pytest.raises(NotImplementedError):
        auth.get_user_oid(_event())
