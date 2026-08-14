from activities import moderate_image
from shared import moderation

_IMAGE_KEY = "uploads/photo.jpg"


def _patch_storage(monkeypatch, exists=True):
    monkeypatch.setattr(moderate_image.storage, "object_exists", lambda key: exists)


def _patch_verdict(monkeypatch, verdict, categories=()):
    seen = {}

    def fake_analyze(image_key):
        seen["image_key"] = image_key
        return {"verdict": verdict, "categories": list(categories), "detail": None}

    monkeypatch.setattr(moderate_image.moderation, "analyze_image", fake_analyze)
    return seen


def test_safe_image_is_allowed(monkeypatch):
    _patch_storage(monkeypatch)
    _patch_verdict(monkeypatch, moderation.Verdict.SAFE)

    result = moderate_image.run({"image_key": _IMAGE_KEY})

    assert result["allowed"] is True
    assert result["reason"] is None


def test_unsafe_image_is_blocked_with_a_readable_reason(monkeypatch):
    _patch_storage(monkeypatch)
    _patch_verdict(monkeypatch, moderation.Verdict.UNSAFE, ["Sexual", "Violence"])

    result = moderate_image.run({"image_key": _IMAGE_KEY})

    assert result["allowed"] is False
    assert result["categories"] == ["Sexual", "Violence"]
    # Lands on the job as error_message and is shown to the user.
    assert result["reason"] == "This photo was rejected by image moderation (Sexual, Violence)."


def test_unchecked_image_is_allowed(monkeypatch):
    """Fail open on 'could not check' - see the decision in shared/moderation.py."""
    _patch_storage(monkeypatch)
    _patch_verdict(monkeypatch, moderation.Verdict.UNCHECKED)

    result = moderate_image.run({"image_key": _IMAGE_KEY})

    assert result["allowed"] is True
    assert result["verdict"] == moderation.Verdict.UNCHECKED


def test_missing_image_is_blocked_without_calling_moderation(monkeypatch):
    """'There is no image' is not the same as 'I could not check the image', and
    must not be waved through by the fail-open rule."""
    _patch_storage(monkeypatch, exists=False)

    def explode(image_key):
        raise AssertionError("moderation must not be called for a missing object")

    monkeypatch.setattr(moderate_image.moderation, "analyze_image", explode)

    result = moderate_image.run({"image_key": _IMAGE_KEY})

    assert result["allowed"] is False
    assert result["verdict"] == moderate_image.MISSING
    assert "never finished uploading" in result["reason"]


def test_moderation_receives_the_object_key_not_a_url(monkeypatch):
    """Rekognition reads the object straight out of S3. The Azure service had to
    fetch it over the internet with a SAS attached, which is also why moderation
    could never work against a local emulator."""
    _patch_storage(monkeypatch)
    seen = _patch_verdict(monkeypatch, moderation.Verdict.SAFE)

    moderate_image.run({"image_key": _IMAGE_KEY})

    assert seen["image_key"] == _IMAGE_KEY
