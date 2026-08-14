"""The culinary-technique similarity search, end to end against a real table.

Was `VECTOR_DISTANCE` against a `VECTOR(1536)` column in SQL Server 2025. The
comparison is now done in-process over the whole EMBEDDINGS partition, so what is
integration-tested here is the read path plus the float round trip - the maths
itself is unit-tested in tests/unit/test_vectors.py.
"""

import pytest

from activities import query_culinary_embeddings as query_embeddings
from db.seed_embeddings import SEED_TECHNIQUES, seed
from shared import repository

pytestmark = pytest.mark.integration


def test_query_returns_top_k_with_the_expected_shape(ddb_table):
    seed()

    results = query_embeddings.run({"query_text": "roux thickened gravy", "top_k": 5})

    assert len(results) == 5
    for result in results:
        assert set(result.keys()) == {"embedding_id", "source_text", "cuisine_type", "distance"}
    # The raw vector must not come back - these results become Step Functions task
    # output, where a 1024-float array per row would eat the state payload budget.
    assert all("embedding" not in result for result in results)


def test_results_ordered_by_ascending_distance(ddb_table):
    seed()

    results = query_embeddings.run({"query_text": "blooming spices in hot oil", "top_k": 8})

    distances = [result["distance"] for result in results]
    assert distances == sorted(distances)


def test_seeding_is_idempotent(ddb_table):
    """Stable ids derived from the source text, so re-running cannot duplicate."""
    seed()
    seed()

    assert len(repository.all_embeddings()) == len(SEED_TECHNIQUES)


def test_embedding_floats_survive_the_decimal_round_trip(ddb_table):
    seed()

    embeddings = repository.all_embeddings()

    vector = embeddings[0]["embedding"]
    assert len(vector) == 1024
    assert all(isinstance(value, float) for value in vector)


def test_empty_corpus_returns_no_results(ddb_table):
    """No seed data: the activity must return [] rather than raising."""
    for embedding in repository.all_embeddings():
        from shared import ddb as ddb_module

        ddb_module.delete(ddb_module.EMBEDDINGS_PK, ddb_module.technique_sk(embedding["embedding_id"]))

    assert query_embeddings.run({"query_text": "anything", "top_k": 5}) == []
