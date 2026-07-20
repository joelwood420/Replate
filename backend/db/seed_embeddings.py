"""Seed CulinaryEmbeddings with a handful of stub culinary-technique rows.

Phase 1 stub: SourceText/CuisineType are hand-written and Embedding is a
deterministic pseudo-embedding (shared.models.pseudo_embedding), not a real
embedding-model call - swap for a real embedding pipeline in Phase 3.

Run directly: `python db/seed_embeddings.py` (from backend/).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import db, models  # noqa: E402

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


def seed(conn) -> int:
    cursor = conn.cursor()
    inserted = 0
    for technique in SEED_TECHNIQUES:
        cursor.execute(
            "SELECT COUNT(*) FROM CulinaryEmbeddings WHERE SourceText = ?",
            technique["source_text"],
        )
        if cursor.fetchone()[0] > 0:
            continue

        embedding_json = json.dumps(models.pseudo_embedding(technique["source_text"]))
        cursor.execute(
            "INSERT INTO CulinaryEmbeddings (SourceText, Embedding, CuisineType, SourceUrl) "
            "VALUES (?, CAST(CAST(? AS NVARCHAR(MAX)) AS VECTOR(1536)), ?, ?)",
            technique["source_text"],
            embedding_json,
            technique["cuisine_type"],
            technique["source_url"],
        )
        inserted += 1
    return inserted


if __name__ == "__main__":
    with db.get_connection() as connection:
        count = seed(connection)
    print(f"Inserted {count} new CulinaryEmbeddings row(s) (skipped rows that already existed).")
