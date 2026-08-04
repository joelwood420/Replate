"""Azure AI Content Safety image moderation (CLAUDE.md Phase 3 step 6).

Called on the uploaded photo before anything else in the pipeline, so a rejected
image costs one moderation call and no AI spend at all.

FAILURE MODE (decision of 2026-08-05, see docs/decisions.md): an explicit unsafe
verdict blocks the job, but a service error, timeout, missing configuration or
exhausted quota does not. "This image is unsafe" and "I could not check this image"
are different answers and are reported as different verdicts. The F0 tier rejects
requests outright once its 5,000 images/month allowance is gone, and treating that
as unsafe would take scanning offline for the rest of the calendar month.

The image is passed by SAS URL for the service to fetch itself, rather than piping
the bytes back out through the Function App.
"""

import logging

import httpx

from shared import config

API_VERSION = "2024-09-01"


class Verdict:
    SAFE = "safe"
    UNSAFE = "unsafe"
    #: The check did not complete. Callers allow these through - see the module docstring.
    UNCHECKED = "unchecked"


def is_configured() -> bool:
    return bool(config.content_safety_endpoint() and config.content_safety_key())


def _analyze_url() -> str:
    endpoint = config.content_safety_endpoint().rstrip("/")
    return f"{endpoint}/contentsafety/image:analyze?api-version={API_VERSION}"


def _unchecked(detail: str) -> dict:
    logging.warning("Content Safety check did not complete, allowing image through: %s", detail)
    return {"verdict": Verdict.UNCHECKED, "categories": [], "detail": detail}


def analyze_image(image_url: str) -> dict:
    """Analyze an image by URL.

    `image_url` must be fetchable by the Content Safety service - for the private
    uploads container that means a read SAS URL, which shared/blob.py mints.

    Returns `{"verdict": ..., "categories": [...], "detail": ...}`, where categories
    lists the categories that met the rejection threshold (only ever populated on an
    unsafe verdict).
    """
    if not is_configured():
        return _unchecked("CONTENT_SAFETY_ENDPOINT/CONTENT_SAFETY_KEY are not set")

    headers = {
        "Ocp-Apim-Subscription-Key": config.content_safety_key(),
        "Content-Type": "application/json",
    }
    body = {"image": {"blobUrl": image_url}}
    threshold = config.content_safety_reject_severity()

    last_error = "no attempts were made"
    for _ in range(config.content_safety_max_retries() + 1):
        try:
            response = httpx.post(
                _analyze_url(),
                json=body,
                headers=headers,
                timeout=config.content_safety_timeout_seconds(),
            )
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        if response.status_code >= 400:
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            # On F0 a 429 means the monthly allowance is spent, not that this caller
            # is going too fast, so retrying cannot help. 4xx generally means the
            # request itself is wrong - also not worth repeating.
            if response.status_code < 500:
                break
            continue

        try:
            analysis = response.json().get("categoriesAnalysis", [])
        except ValueError as exc:
            last_error = f"unparseable response: {exc}"
            continue

        flagged = [entry for entry in analysis if (entry.get("severity") or 0) >= threshold]
        if flagged:
            return {
                "verdict": Verdict.UNSAFE,
                "categories": [entry.get("category", "Unknown") for entry in flagged],
                "detail": None,
            }
        return {"verdict": Verdict.SAFE, "categories": [], "detail": None}

    return _unchecked(last_error)
