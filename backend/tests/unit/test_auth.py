import azure.functions as func
import pytest

from shared import auth


def test_stub_mode_uses_header_and_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(auth.config, "entraid_enabled", lambda: False)

    req_with_header = func.HttpRequest(
        method="POST", url="/api/jobs", body=b"{}", headers={"X-Debug-User-Oid": "explicit-oid"}
    )
    assert auth.get_user_oid(req_with_header) == "explicit-oid"

    req_without_header = func.HttpRequest(method="POST", url="/api/jobs", body=b"{}", headers={})
    assert auth.get_user_oid(req_without_header) == auth.config.stub_default_user_oid()


def test_entraid_enabled_raises_not_implemented(monkeypatch):
    monkeypatch.setattr(auth.config, "entraid_enabled", lambda: True)

    req = func.HttpRequest(method="POST", url="/api/jobs", body=b"{}", headers={})
    with pytest.raises(NotImplementedError):
        auth.get_user_oid(req)
