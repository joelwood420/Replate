from unittest.mock import MagicMock

from activities import query_culinary_embeddings as query_embeddings
from shared import models


def _mock_conn(rows):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = rows
    return conn


def test_builds_parameterized_vector_distance_query():
    conn = _mock_conn(rows=[])

    query_embeddings._execute({"query_text": "pad thai", "top_k": 3}, conn)

    call = conn.cursor().execute.call_args
    sql_text = call.args[0]
    params = call.args[1:]
    assert "VECTOR_DISTANCE" in sql_text
    assert "pad thai" not in sql_text
    assert params[0] == 3


def test_returns_top_k_ordered_by_ascending_distance():
    rows = [
        MagicMock(EmbeddingId="e1", SourceText="a", CuisineType="Thai", Distance=0.1),
        MagicMock(EmbeddingId="e2", SourceText="b", CuisineType="Thai", Distance=0.5),
    ]
    conn = _mock_conn(rows=rows)

    result = query_embeddings._execute({"query_text": "pad thai", "top_k": 2}, conn)

    assert [r["distance"] for r in result] == [0.1, 0.5]
    assert result[0]["embedding_id"] == "e1"


def test_stub_query_embedding_is_deterministic_for_same_text():
    first = models.pseudo_embedding("roux")
    second = models.pseudo_embedding("roux")

    assert first == second
