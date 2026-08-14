"""Seed the EMBEDDINGS partition with a handful of stub culinary-technique items.

Phase 0 stub: source_text/cuisine_type are hand-written and the vector is a
deterministic pseudo-embedding (shared.models.pseudo_embedding), not a real
embedding-model call - swap for Bedrock Titan Text Embeddings V2 in Phase 3.

Run directly: `python db/seed_embeddings.py` (from backend/).
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import models, repository  # noqa: E402

SEED_TECHNIQUES = [
    {
        "source_text": (
            "Deglazing a pan: after searing meat, add wine or stock to a hot pan and "
            "scrape up the browned fond to build a pan sauce."
        ),
        "cuisine_type": "French",
        "source_url": None,
    },
    {
        "source_text": (
            "Tempering egg yolks: slowly whisk hot liquid into beaten egg yolks before "
            "combining, to avoid scrambling the eggs when making custards or carbonara."
        ),
        "cuisine_type": "General",
        "source_url": None,
    },
    {
        "source_text": (
            "Making a roux: cook equal parts fat and flour together until golden, then "
            "whisk in liquid gradually to thicken sauces, gumbo, or gravy."
        ),
        "cuisine_type": "Cajun",
        "source_url": None,
    },
    {
        "source_text": (
            "Blooming spices: toast whole or ground spices briefly in hot oil or ghee to "
            "release their aromatic oils before adding other ingredients."
        ),
        "cuisine_type": "Indian",
        "source_url": None,
    },
    {
        "source_text": (
            "Velveting meat: coat thinly sliced meat in a mixture of egg white, "
            "cornstarch, and rice wine before a brief blanch or oil-poach, for a silky "
            "tender stir-fry texture."
        ),
        "cuisine_type": "Chinese",
        "source_url": None,
    },
    {
        "source_text": (
            "Building a sofrito: slowly cook finely diced onion, garlic, and peppers in "
            "olive oil as an aromatic base for stews, rice dishes, and sauces."
        ),
        "cuisine_type": "Spanish",
        "source_url": None,
    },
    {
        "source_text": (
            "Emulsifying vinaigrette: whisk oil into an acid (vinegar or citrus) slowly "
            "and steadily, with a touch of mustard as an emulsifier, to keep it from "
            "separating."
        ),
        "cuisine_type": "General",
        "source_url": None,
    },
    {
        "source_text": (
            "Nixtamalization: soak and cook dried corn in an alkaline solution (lime "
            "water) to soften it and unlock its nutrients before grinding into masa."
        ),
        "cuisine_type": "Mexican",
        "source_url": None,
    },
]


def _stable_id(source_text: str) -> str:
    """Derive the item id from the text it embeds.

    Makes re-seeding idempotent by construction: the same technique always lands
    on the same key and overwrites itself, so there is no "does this row already
    exist?" query and no chance of accumulating duplicates across runs.
    """
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:16]


def seed() -> int:
    for technique in SEED_TECHNIQUES:
        repository.put_embedding(
            source_text=technique["source_text"],
            embedding=models.pseudo_embedding(technique["source_text"]),
            cuisine_type=technique["cuisine_type"],
            source_url=technique["source_url"],
            embedding_id=_stable_id(technique["source_text"]),
        )
    return len(SEED_TECHNIQUES)


if __name__ == "__main__":
    count = seed()
    print(f"Seeded {count} culinary-technique embedding(s) (idempotent - safe to re-run).")
