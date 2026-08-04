"""Stage 1's first activity: moderate the uploaded photo before spending anything.

Deliberately runs ahead of every other activity in dish_orchestrator. It gates the
whole pipeline, so a rejected image costs one Content Safety call and no AI spend -
which is the entire point of putting it here rather than next to the vision step.

A MISSING blob is reported separately from a failed check and is NOT covered by the
fail-open rule. "The service could not check this image" is a reason to continue;
"there is no image" is not - it means the client never finished uploading, and
passing that downstream just fails the vision call a step later with a far less
obvious error.
"""

import azure.durable_functions as df

from shared import blob, content_safety

bp = df.Blueprint()

#: Verdict for a blob URL that was handed out but never uploaded to. Not a Content
#: Safety verdict - the service is never called in this case.
MISSING = "missing"


def run(activity_input: dict) -> dict:
    """Returns `{"allowed": bool, "verdict": ..., "categories": [...], "reason": ...}`.

    `reason` is written for the user - it lands in Jobs.ErrorMessage and is shown in
    the app - so it is populated only when the image is rejected.
    """
    blob_url = activity_input["image_blob_url"]

    if not blob.blob_exists(blob_url):
        return {
            "allowed": False,
            "verdict": MISSING,
            "categories": [],
            "reason": "The photo was never finished uploading. Try scanning it again.",
        }

    result = content_safety.analyze_image(blob.generate_read_sas_url(blob_url))

    if result["verdict"] == content_safety.Verdict.UNSAFE:
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


@bp.activity_trigger(input_name="activityInput")
def moderate_image(activityInput: dict) -> dict:
    return run(activityInput)
