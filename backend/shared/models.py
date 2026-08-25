from __future__ import annotations

import hashlib
import struct

# Amazon Titan Text Embeddings V2. Was 1536 (Azure OpenAI text-embedding-3-small),
# which had to match the width of a `VECTOR(1536)` column. Now that vectors live in
# DynamoDB and similarity is computed in-process, the width is only a constant -
# nothing but the seed data has to agree with it.
EMBEDDING_DIM = 1024


class MatchMethod:
    MENU_MATCHED = "menu_matched"
    VISION_ONLY_MEDIUM = "vision_only_medium"
    VISION_ONLY_LOW = "vision_only_low"


class JobStatus:
    """Job lifecycle states.

    The pipeline runs in two stages. Stage 1 (identify the restaurant, fetch its
    menu, guess the dish, match the guess against the menu) runs automatically on
    upload and ends at IDENTIFIED - the dish is in the user's cookbook, but has no
    recipe yet. Stage 2 (recipe generation) only runs when the user asks for it,
    passing through GENERATING to COMPLETED.

    FAILED means stage 1 failed. A stage-2 failure reverts to IDENTIFIED with an
    error message instead, so a transient generator error never discards a good
    menu match - see activities/persist_job_result.mark_recipe_failed.

    CANCELLED means the user aborted an in-flight scan to stop model spend (see
    triggers/job_cancel_http.py). It is a normal terminal outcome, kept distinct
    from FAILED so a deliberate cancel does not read as an error or count towards
    failure metrics.

    Values are stored as the job item's `status` attribute and must be mirrored in
    frontend/src/lib/apiClient.ts and docs/payload-schemas.json.
    """

    QUEUED = "Queued"
    PROCESSING = "Processing"
    IDENTIFIED = "Identified"
    GENERATING = "Generating"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


def candidate_envelope(candidates: list[dict]) -> dict:
    """Shape a candidate list for the state machine.

    The restaurant-lookup activities return a plain list, but ASL cannot express
    "is this list empty" or "take the first element if there is one" without
    awkward JSONPath. Flattening the decision into explicit fields here keeps the
    Choice state in dish-identify.asl.json to a single boolean check, and keeps
    the fallback logic in Python where it can be tested.
    """
    top = candidates[0] if candidates else None
    return {
        "candidates": candidates,
        "top_candidate": top,
        "candidate_found": top is not None,
        "restaurant_id": top["restaurant_id"] if top else None,
    }


def pseudo_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic stand-in for a real embedding-model call.

    Hashes `text` into a repeatable stream of floats in [-1, 1] so distance
    ordering between texts is stable without calling a real embedding API.
    Not semantically meaningful - swap for a real embedding call in Phase 3.
    """
    values: list[float] = []
    counter = 0
    while len(values) < dim:
        digest = hashlib.sha256(f"{text}:{counter}".encode("utf-8")).digest()
        for i in range(0, len(digest), 4):
            if len(values) >= dim:
                break
            chunk = digest[i : i + 4]
            if len(chunk) < 4:
                continue
            (as_uint,) = struct.unpack(">I", chunk)
            values.append((as_uint / 0xFFFFFFFF) * 2 - 1)
        counter += 1
    return values
