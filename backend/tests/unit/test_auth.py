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


def test_cognito_enabled_reads_verified_sub_claim(monkeypatch):
    """With Cognito on, the API Gateway JWT authorizer has already validated the
    token, so get_user_oid just reads the `sub` claim it put on the request."""
    monkeypatch.setattr(auth.config, "cognito_enabled", lambda: True)

    event = _event()
    event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": "cognito-user-123"}}}

    assert auth.get_user_oid(event) == "cognito-user-123"


def test_cognito_enabled_without_claims_raises(monkeypatch):
    """A missing `sub` when Cognito is on means the authorizer isn't wired to the
    route - a misconfiguration, not an untrusted caller. It must fail, not fall back."""
    monkeypatch.setattr(auth.config, "cognito_enabled", lambda: True)

    with pytest.raises(PermissionError):
        auth.get_user_oid(_event())
