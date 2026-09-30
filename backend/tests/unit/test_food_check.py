"""The upload-time food pre-check (shared/food_check.py).

It only ever says "not food" when Rekognition sees nothing food-like at all. Every
uncertain or failed check answers None so the photo goes on to the vision step, which
still makes the final call - a real dish wrongly blocked is the costly mistake.
"""

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from shared import food_check, moderation


class _FakeRekognition:
    def __init__(self, labels=None, error=None):
        self._labels = labels or []
        self._error = error
        self.requests = []

    def detect_labels(self, **request):
        self.requests.append(request)
        if self._error:
            raise self._error
        return {"Labels": self._labels}


@pytest.fixture
def rekognition(monkeypatch):
    monkeypatch.setenv("FOOD_CHECK_ENABLED", "true")
    monkeypatch.setenv("S3_BUCKET_UPLOADS", "uploads-bucket")

    def install(**kwargs):
        client = _FakeRekognition(**kwargs)
        monkeypatch.setattr(moderation, "get_client", lambda: client)
        return client

    return install


def _label(name, parents=(), categories=()):
    return {
        "Name": name,
        "Confidence": 90.0,
        "Parents": [{"Name": p} for p in parents],
        "Categories": [{"Name": c} for c in categories],
    }


def test_disabled_is_unknown_and_never_calls_rekognition(monkeypatch):
    monkeypatch.delenv("FOOD_CHECK_ENABLED", raising=False)
    monkeypatch.setattr(moderation, "get_client", lambda: pytest.fail("should not call"))

    assert food_check.looks_like_food("uploads/p.jpg") is None


def test_a_food_label_is_food(rekognition):
    rekognition(labels=[_label("Food")])

    assert food_check.looks_like_food("uploads/p.jpg") is True


def test_a_specific_dish_with_a_food_parent_is_food(rekognition):
    rekognition(labels=[_label("Pizza", parents=["Food"])])

    assert food_check.looks_like_food("uploads/p.jpg") is True


def test_the_food_and_beverage_category_is_food(rekognition):
    rekognition(labels=[_label("Sushi", categories=["Food and Beverage"])])

    assert food_check.looks_like_food("uploads/p.jpg") is True


def test_a_plate_alone_goes_through_to_the_vision_step(rekognition):
    """An empty plate is not food, but it is the vision step's call, not this one's."""
    rekognition(labels=[_label("Plate", parents=["Tableware"])])

    assert food_check.looks_like_food("uploads/p.jpg") is True


def test_only_non_food_labels_is_not_food(rekognition):
    rekognition(labels=[_label("Cat", parents=["Animal", "Pet"]), _label("Sofa")])

    assert food_check.looks_like_food("uploads/p.jpg") is False


def test_no_labels_at_all_is_unknown_not_rejected(rekognition):
    rekognition(labels=[])

    assert food_check.looks_like_food("uploads/p.jpg") is None


def test_a_service_error_fails_open(rekognition):
    rekognition(
        error=ClientError({"Error": {"Code": "ThrottlingException"}}, "DetectLabels")
    )

    assert food_check.looks_like_food("uploads/p.jpg") is None


def test_a_connection_error_fails_open(rekognition):
    rekognition(error=EndpointConnectionError(endpoint_url="https://rekognition"))

    assert food_check.looks_like_food("uploads/p.jpg") is None


def test_the_photo_is_read_straight_from_s3(rekognition):
    client = rekognition(labels=[_label("Food")])

    food_check.looks_like_food("uploads/p.jpg")

    image = client.requests[0]["Image"]["S3Object"]
    assert image == {"Bucket": "uploads-bucket", "Name": "uploads/p.jpg"}
