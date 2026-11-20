import httpx
import pytest

from shared import secrets, typesafe_client

CRITERIA = {"item_0": "Eggs Benedict", "none": "None of these"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    secrets.reset_caches()
    monkeypatch.delenv("TYPESAFE_API_KEY_PARAM", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test")
    monkeypatch.setenv("TYPESAFE_MATCH_MODEL", "jev-1.14.0")
    yield
    secrets.reset_caches()


class _FakeClient:
    def __init__(self, payload, status, exc):
        self.payload, self.status, self.exc = payload, status, exc
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if self.exc:
            raise self.exc
        return httpx.Response(self.status, json=self.payload, request=httpx.Request("POST", url))


def _respond(monkeypatch, payload=None, status=200, exc=None):
    fake = _FakeClient(payload, status, exc)
    monkeypatch.setattr(typesafe_client, "get_client", lambda: fake)
    return fake.calls


def test_client_is_shared_across_calls():
    typesafe_client.reset_client_cache()
    try:
        assert typesafe_client.get_client() is typesafe_client.get_client()
    finally:
        typesafe_client.reset_client_cache()


def _answer(choice, probabilities):
    return {"answers": {"answer": {"type": "choice", "choice": choice, "probabilities": probabilities}}}


def test_is_configured_needs_a_key_and_a_model(monkeypatch):
    assert typesafe_client.is_configured() is True
    monkeypatch.setenv("TYPESAFE_MATCH_MODEL", "")
    assert typesafe_client.is_configured() is False
    monkeypatch.setenv("TYPESAFE_MATCH_MODEL", "jev-1.14.0")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    assert typesafe_client.is_configured() is False


def test_ssm_failure_degrades_to_not_configured(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY_PARAM", "/replate/typesafe-api-key")

    def boom(name):
        raise RuntimeError("AccessDenied")

    monkeypatch.setattr(secrets, "get_secure_parameter", boom)
    assert typesafe_client.is_configured() is False


def test_choice_sends_a_typed_question_and_returns_the_pick(monkeypatch):
    calls = _respond(monkeypatch, _answer("item_0", {"item_0": 0.87, "none": 0.13}))

    picked, probability = typesafe_client.choice("state", "which?", CRITERIA)

    assert (picked, probability) == ("item_0", 0.87)
    body = calls[0]["json"]
    assert calls[0]["url"] == typesafe_client.SYSTEMONE_URL
    assert calls[0]["headers"]["Authorization"] == "Bearer ts-test"
    assert body["model"] == "jev-1.14.0"
    assert body["questions"]["answer"] == {"type": "choice", "instructions": "which?", "criteria": CRITERIA}


def test_http_error_raises(monkeypatch):
    _respond(monkeypatch, {"error": "nope"}, status=500)
    with pytest.raises(typesafe_client.TypeSafeError):
        typesafe_client.choice("state", "which?", CRITERIA)


def test_timeout_raises(monkeypatch):
    _respond(monkeypatch, exc=httpx.ReadTimeout("slow"))
    with pytest.raises(typesafe_client.TypeSafeError):
        typesafe_client.choice("state", "which?", CRITERIA)


def test_malformed_response_raises(monkeypatch):
    _respond(monkeypatch, {"answers": {}})
    with pytest.raises(typesafe_client.TypeSafeError):
        typesafe_client.choice("state", "which?", CRITERIA)


def test_option_not_offered_raises(monkeypatch):
    _respond(monkeypatch, _answer("item_9", {"item_9": 1.0}))
    with pytest.raises(typesafe_client.TypeSafeError, match="not offered"):
        typesafe_client.choice("state", "which?", CRITERIA)
