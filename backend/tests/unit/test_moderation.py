"""Rekognition moderation, with the fail-open/fail-closed policy intact.

The policy is the load-bearing part of this module and it is invisible by design:
if the check silently stops working, everything passes and nothing looks broken.
So the failure modes get more coverage than the happy path.
"""

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from shared import moderation

_KEY = "uploads/photo.jpg"


@pytest.fixture(autouse=True)
def enable_moderation(monkeypatch):
    monkeypatch.setenv("MODERATION_ENABLED", "true")
    monkeypatch.setenv("S3_BUCKET_UPLOADS", "replate-uploads")
    moderation.reset_client_cache()
    yield
    moderation.reset_client_cache()


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def detect_moderation_labels(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "DetectModerationLabels")


def _patch_client(monkeypatch, *responses):
    client = _FakeClient(responses)
    monkeypatch.setattr(moderation, "get_client", lambda: client)
    return client


# --- verdicts ---------------------------------------------------------------


def test_no_labels_is_safe(monkeypatch):
    _patch_client(monkeypatch, {"ModerationLabels": []})

    assert moderation.analyze_image(_KEY)["verdict"] == moderation.Verdict.SAFE


def test_labels_above_the_threshold_are_unsafe(monkeypatch):
    _patch_client(
        monkeypatch,
        {"ModerationLabels": [{"Name": "Explicit Nudity", "ParentName": "Nudity", "Confidence": 96.0}]},
    )

    result = moderation.analyze_image(_KEY)

    assert result["verdict"] == moderation.Verdict.UNSAFE
    # The parent category reads better in the message shown to the user.
    assert result["categories"] == ["Nudity"]


def test_a_label_without_a_parent_falls_back_to_its_own_name(monkeypatch):
    _patch_client(monkeypatch, {"ModerationLabels": [{"Name": "Violence", "Confidence": 91.0}]})

    assert moderation.analyze_image(_KEY)["categories"] == ["Violence"]


def test_duplicate_parents_are_collapsed(monkeypatch):
    _patch_client(
        monkeypatch,
        {
            "ModerationLabels": [
                {"Name": "Graphic Violence", "ParentName": "Violence", "Confidence": 95.0},
                {"Name": "Weapons", "ParentName": "Violence", "Confidence": 92.0},
            ]
        },
    )

    assert moderation.analyze_image(_KEY)["categories"] == ["Violence"]


# --- the image is read from S3, not fetched over the internet ---------------


def test_the_object_is_read_directly_from_s3(monkeypatch):
    """No presigned URL round-trip - the image never leaves the account. This is
    also why moderation can work locally now, which it never could against Azurite."""
    client = _patch_client(monkeypatch, {"ModerationLabels": []})

    moderation.analyze_image(_KEY)

    assert client.calls[0]["Image"] == {
        "S3Object": {"Bucket": "replate-uploads", "Name": _KEY}
    }


def test_the_confidence_threshold_is_passed_through(monkeypatch):
    monkeypatch.setenv("MODERATION_MIN_CONFIDENCE", "65")
    client = _patch_client(monkeypatch, {"ModerationLabels": []})

    moderation.analyze_image(_KEY)

    assert client.calls[0]["MinConfidence"] == 65.0


# --- fail-open on "could not check" -----------------------------------------


def test_unconfigured_is_unchecked_not_unsafe(monkeypatch):
    """Local dev has no moderation configured and must still work."""
    monkeypatch.setenv("MODERATION_ENABLED", "false")

    assert moderation.analyze_image(_KEY)["verdict"] == moderation.Verdict.UNCHECKED


def test_a_throttled_call_is_retried_then_unchecked(monkeypatch):
    monkeypatch.setenv("MODERATION_MAX_RETRIES", "2")
    client = _patch_client(
        monkeypatch,
        _client_error("ThrottlingException"),
        _client_error("ThrottlingException"),
        _client_error("ThrottlingException"),
    )

    result = moderation.analyze_image(_KEY)

    assert result["verdict"] == moderation.Verdict.UNCHECKED
    assert len(client.calls) == 3


def test_a_transient_error_can_succeed_on_retry(monkeypatch):
    client = _patch_client(
        monkeypatch, _client_error("InternalServerError"), {"ModerationLabels": []}
    )

    assert moderation.analyze_image(_KEY)["verdict"] == moderation.Verdict.SAFE
    assert len(client.calls) == 2


def test_a_network_timeout_is_unchecked(monkeypatch):
    monkeypatch.setenv("MODERATION_MAX_RETRIES", "0")
    _patch_client(monkeypatch, ReadTimeoutError(endpoint_url="https://rekognition"))

    assert moderation.analyze_image(_KEY)["verdict"] == moderation.Verdict.UNCHECKED


@pytest.mark.parametrize(
    "code", ["AccessDeniedException", "InvalidImageFormatException", "ImageTooLargeException"]
)
def test_a_fatal_error_is_not_retried(monkeypatch, code):
    """Retrying a denied permission or a malformed image cannot help - it just
    triples the latency before the same answer."""
    monkeypatch.setenv("MODERATION_MAX_RETRIES", "3")
    client = _patch_client(monkeypatch, _client_error(code), {"ModerationLabels": []})

    result = moderation.analyze_image(_KEY)

    assert result["verdict"] == moderation.Verdict.UNCHECKED
    assert len(client.calls) == 1


def test_the_reason_for_being_unchecked_is_reported(monkeypatch):
    """Invisible failure is the risk here, so the detail has to survive to the logs."""
    monkeypatch.setenv("MODERATION_MAX_RETRIES", "0")
    _patch_client(monkeypatch, _client_error("AccessDeniedException"))

    assert "AccessDeniedException" in moderation.analyze_image(_KEY)["detail"]


def test_unchecked_never_reports_categories(monkeypatch):
    monkeypatch.setenv("MODERATION_ENABLED", "false")

    assert moderation.analyze_image(_KEY)["categories"] == []
