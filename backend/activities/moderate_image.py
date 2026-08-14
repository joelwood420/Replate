"""Stage 1's first activity: moderate the uploaded photo before spending anything.

Deliberately runs ahead of every other task in dish-identify.asl.json. It gates the
whole pipeline, so a rejected image costs one Rekognition call and no model spend -
which is the entire point of putting it here rather than next to the vision step.

A MISSING object is reported separately from a failed check and is NOT covered by the
fail-open rule. "The service could not check this image" is a reason to continue;
"there is no image" is not - it means the client never finished uploading, and
passing that downstream just fails the vision call a step later with a far less
obvious error.
"""


from shared import moderation, storage

#: Verdict for an object key that was handed out but never uploaded to. Not a
#: moderation verdict - the service is never called in this case.
MISSING = "missing"


def run(activity_input: dict) -> dict:
    """Returns `{"allowed": bool, "verdict": ..., "categories": [...], "reason": ...}`.

    `reason` is written for the user - it lands on the job as `error_message` and is
    shown in the app - so it is populated only when the image is rejected.
    """
    image_key = activity_input["image_key"]

    if not storage.object_exists(image_key):
        return {
            "allowed": False,
            "verdict": MISSING,
            "categories": [],
            "reason": "The photo was never finished uploading. Try scanning it again.",
        }

    # The key, not a URL: Rekognition reads the object straight out of S3, so the
    # image never leaves the account and there is no presigned round-trip.
    result = moderation.analyze_image(image_key)

    if result["verdict"] == moderation.Verdict.UNSAFE:
        categories = ", ".join(result["categories"]) or "unknown"
        return {
            "allowed": False,
            "verdict": result["verdict"],
            "categories": result["categories"],
            "reason": f"This photo was rejected by image moderation ({categories}).",
        }

    return {
        "allowed": True,
        "verdict": result["verdict"],
        "categories": [],
        "reason": None,
    }


def handler(event, context=None):
    """Lambda entry point for the ModerateImage task in statemachines/dish-identify.asl.json."""
    return run(event)
