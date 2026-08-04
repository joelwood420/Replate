import httpx
import pytest

from shared import content_safety

_IMAGE_URL = "https://acct.blob.core.windows.net/uploads/photo.jpg?sig=abc"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_ENDPOINT", "https://cs.cognitiveservices.azure.com/")
    monkeypatch.setenv("CONTENT_SAFETY_KEY", "test-key")
    monkeypatch.setenv("CONTENT_SAFETY_MAX_RETRIES", "2")


class _Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _analysis(**severities):
    return {"categoriesAnalysis": [{"category": k, "severity": v} for k, v in severities.items()]}


def _patch_post(monkeypatch, *responses):
    """Return each response in turn, recording every call."""
    calls = []
    queue = list(responses)

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        result = queue.pop(0) if queue else responses[-1]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(content_safety.httpx, "post", fake_post)
    return calls


def test_clean_image_is_safe(monkeypatch):
    _patch_post(monkeypatch, _Response(payload=_analysis(Hate=0, SelfHarm=0, Sexual=0, Violence=0)))

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.SAFE
    assert result["categories"] == []


def test_image_at_or_above_the_threshold_is_unsafe(monkeypatch):
    _patch_post(monkeypatch, _Response(payload=_analysis(Hate=0, Sexual=6, Violence=4)))

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.UNSAFE
    assert sorted(result["categories"]) == ["Sexual", "Violence"]


def test_low_severity_does_not_reject(monkeypatch):
    """Severity 2 is the 'low' band. A plausible food photo can land there - a rare
    steak reading low on Violence - so the default threshold is above it."""
    _patch_post(monkeypatch, _Response(payload=_analysis(Violence=2)))

    assert content_safety.analyze_image(_IMAGE_URL)["verdict"] == content_safety.Verdict.SAFE


def test_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_REJECT_SEVERITY", "2")
    _patch_post(monkeypatch, _Response(payload=_analysis(Violence=2)))

    assert content_safety.analyze_image(_IMAGE_URL)["verdict"] == content_safety.Verdict.UNSAFE


def test_sends_the_image_by_url_with_the_subscription_key(monkeypatch):
    calls = _patch_post(monkeypatch, _Response(payload=_analysis(Violence=0)))

    content_safety.analyze_image(_IMAGE_URL)

    assert calls[0]["json"] == {"image": {"blobUrl": _IMAGE_URL}}
    assert calls[0]["headers"]["Ocp-Apim-Subscription-Key"] == "test-key"
    # No double slash - the endpoint app setting comes back with a trailing one.
    assert calls[0]["url"] == (
        "https://cs.cognitiveservices.azure.com/contentsafety/image:analyze"
        f"?api-version={content_safety.API_VERSION}"
    )


def test_missing_configuration_is_unchecked_not_a_crash(monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_ENDPOINT", "")

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.UNCHECKED
    assert content_safety.is_configured() is False


def test_exhausted_free_tier_is_unchecked_and_not_retried(monkeypatch):
    """F0 returns 429 when the monthly allowance is gone, which retrying cannot fix.
    Treating it as unsafe would take scanning offline until the next month."""
    calls = _patch_post(monkeypatch, _Response(status_code=429, text="quota exceeded"))

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.UNCHECKED
    assert len(calls) == 1


def test_server_error_is_retried_then_unchecked(monkeypatch):
    calls = _patch_post(monkeypatch, _Response(status_code=503, text="unavailable"))

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.UNCHECKED
    assert len(calls) == 3  # initial attempt + CONTENT_SAFETY_MAX_RETRIES


def test_transient_error_recovers_on_retry(monkeypatch):
    _patch_post(
        monkeypatch,
        httpx.ConnectTimeout("timed out"),
        _Response(payload=_analysis(Violence=6)),
    )

    assert content_safety.analyze_image(_IMAGE_URL)["verdict"] == content_safety.Verdict.UNSAFE


def test_network_failure_is_unchecked(monkeypatch):
    _patch_post(monkeypatch, httpx.ConnectError("no route to host"))

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.UNCHECKED
    assert "ConnectError" in result["detail"]


def test_bad_key_is_unchecked_and_not_retried(monkeypatch):
    calls = _patch_post(monkeypatch, _Response(status_code=401, text="access denied"))

    result = content_safety.analyze_image(_IMAGE_URL)

    assert result["verdict"] == content_safety.Verdict.UNCHECKED
    assert len(calls) == 1
    assert "401" in result["detail"]
