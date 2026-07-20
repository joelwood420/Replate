import pytest

from db.seed_embeddings import seed
from activities import query_culinary_embeddings as query_embeddings

pytestmark = pytest.mark.integration


def test_vector_distance_query_against_seeded_embeddings(sql_connection):
    seed(sql_connection)
    sql_connection.commit()

    results = query_embeddings._execute({"query_text": "roux thickened gravy", "top_k": 5}, sql_connection)

    assert len(results) == 5
    for result in results:
        assert set(result.keys()) == {"embedding_id", "source_text", "cuisine_type", "distance"}


def test_results_ordered_by_ascending_distance(sql_connection):
    seed(sql_connection)
    sql_connection.commit()

    results = query_embeddings._execute({"query_text": "blooming spices in hot oil", "top_k": 8}, sql_connection)

    distances = [r["distance"] for r in results]
    assert distances == sorted(distances)
