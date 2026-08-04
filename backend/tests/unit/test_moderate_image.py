from activities import moderate_image
from shared import content_safety

_BLOB_URL = "https://acct.blob.core.windows.net/uploads/photo.jpg"


def _patch_blob(monkeypatch, exists=True):
    monkeypatch.setattr(moderate_image.blob, "blob_exists", lambda url: exists)
    monkeypatch.setattr(moderate_image.blob, "generate_read_sas_url", lambda url: f"{url}?sig=abc")


def _patch_verdict(monkeypatch, verdict, categories=()):
    seen = {}

    def fake_analyze(url):
        seen["url"] = url
        return {"verdict": verdict, "categories": list(categories), "detail": None}

    monkeypatch.setattr(moderate_image.content_safety, "analyze_image", fake_analyze)
    return seen


def test_safe_image_is_allowed(monkeypatch):
    _patch_blob(monkeypatch)
    _patch_verdict(monkeypatch, content_safety.Verdict.SAFE)

    result = moderate_image.run({"image_blob_url": _BLOB_URL})

    assert result["allowed"] is True
    assert result["reason"] is None


def test_unsafe_image_is_blocked_with_a_readable_reason(monkeypatch):
    _patch_blob(monkeypatch)
    _patch_verdict(monkeypatch, content_safety.Verdict.UNSAFE, ["Sexual", "Violence"])

    result = moderate_image.run({"image_blob_url": _BLOB_URL})

    assert result["allowed"] is False
    assert result["categories"] == ["Sexual", "Violence"]
    # Lands in Jobs.ErrorMessage and is shown to the user.
    assert result["reason"] == "This photo was rejected by image moderation (Sexual, Violence)."


def test_unchecked_image_is_allowed(monkeypatch):
    """Fail open on 'could not check' - see the decision in shared/content_safety.py."""
    _patch_blob(monkeypatch)
    _patch_verdict(monkeypatch, content_safety.Verdict.UNCHECKED)

    result = moderate_image.run({"image_blob_url": _BLOB_URL})

    assert result["allowed"] is True
    assert result["verdict"] == content_safety.Verdict.UNCHECKED


def test_missing_image_is_blocked_without_calling_content_safety(monkeypatch):
    """'There is no image' is not the same as 'I could not check the image', and
    must not be waved through by the fail-open rule."""
    _patch_blob(monkeypatch, exists=False)

    def explode(url):
        raise AssertionError("Content Safety must not be called for a missing blob")

    monkeypatch.setattr(moderate_image.content_safety, "analyze_image", explode)

    result = moderate_image.run({"image_blob_url": _BLOB_URL})

    assert result["allowed"] is False
    assert result["verdict"] == moderate_image.MISSING
    assert "never finished uploading" in result["reason"]


def test_analyzes_a_read_sas_url_not_the_bare_blob_url(monkeypatch):
    """The uploads container is private, so the service can only fetch the image
    with a SAS attached."""
    _patch_blob(monkeypatch)
    seen = _patch_verdict(monkeypatch, content_safety.Verdict.SAFE)

    moderate_image.run({"image_blob_url": _BLOB_URL})

    assert seen["url"] == f"{_BLOB_URL}?sig=abc"
