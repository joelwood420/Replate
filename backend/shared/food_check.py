"""Fast "is this a plate of food?" pre-check via Amazon Rekognition DetectLabels.

Runs synchronously in POST /api/jobs/{jobId}/uploaded, before the job is queued, so a
non-food photo is reported in about a second instead of after the ~10s vision call. The
point is the moment it happens: the diner snaps the dish and puts the phone away, and
if the photo is unusable they need to know while the plate is still in front of them
(docs/decisions.md, 2026-10-01).

It is a coarse filter, not the judge. The vision step still makes the final is_food
call, so this only ever says "not food" when Rekognition sees nothing food-like at all.
Anything uncertain, and every service error, answers None and the photo goes through
to the pipeline as it did before this check existed - the same fail-open rule as
moderation (see shared/moderation.py).
"""

import logging

from botocore.exceptions import BotoCoreError, ClientError

from shared import config as app_config
from shared import moderation

#: Label names that count as a food signal. Tableware is here on purpose: an empty
#: plate is not food, but a plate is a strong enough hint that the vision step, not
#: this pre-check, should make that call.
_FOOD_LABELS = {
    "food",
    "meal",
    "dish",
    "dinner",
    "lunch",
    "breakfast",
    "brunch",
    "dessert",
    "beverage",
    "drink",
    "plate",
    "bowl",
    "cutlery",
    "tableware",
}

#: Rekognition's label category for anything edible or drinkable.
_FOOD_CATEGORY = "food and beverage"


def _is_food_label(label: dict) -> bool:
    names = {label.get("Name", "")}
    names.update(parent.get("Name", "") for parent in label.get("Parents", []))
    if {name.lower() for name in names} & _FOOD_LABELS:
        return True
    return any(
        category.get("Name", "").lower() == _FOOD_CATEGORY
        for category in label.get("Categories", [])
    )


def looks_like_food(image_key: str) -> bool | None:
    """True if the photo shows food, False if clearly not, None if unknown.

    None covers "check disabled" and every failure. Callers must treat it the same as
    True: continue to the full pipeline.
    """
    if not app_config.food_check_enabled():
        return None

    try:
        response = moderation.get_client().detect_labels(
            Image={
                "S3Object": {"Bucket": app_config.s3_bucket_uploads(), "Name": image_key}
            },
            MaxLabels=25,
            MinConfidence=app_config.food_check_min_confidence(),
        )
    except (ClientError, BotoCoreError) as exc:
        logging.warning("Food pre-check did not complete, letting the photo through: %s", exc)
        return None

    labels = response.get("Labels", [])
    if not labels:
        # Nothing recognised at all (a very dark or blurry shot). Too uncertain to
        # block; let the vision step look at it.
        return None
    if any(_is_food_label(label) for label in labels):
        return True

    logging.info(
        "Food pre-check found no food labels: %s",
        ", ".join(label.get("Name", "?") for label in labels[:10]),
    )
    return False
