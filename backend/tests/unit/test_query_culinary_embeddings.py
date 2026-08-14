from activities import query_culinary_embeddings as query_embeddings
from shared import models, repository


def _seed(texts):
    for index, text in enumerate(texts):
        repository.put_embedding(
            source_text=text,
            embedding=models.pseudo_embedding(text),
            cuisine_type="Thai",
            embedding_id=f"e{index}",
        )


def test_returns_at_most_top_k(ddb_table):
    _seed(["a", "b", "c", "d"])

    result = query_embeddings.run({"query_text": "pad thai", "top_k": 2})

    assert len(result) == 2


def test_results_ordered_by_ascending_distance(ddb_table):
    _seed(["a", "b", "c"])

    result = query_embeddings.run({"query_text": "pad thai", "top_k": 3})

    distances = [r["distance"] for r in result]
    assert distances == sorted(distances)


def test_exact_text_match_is_the_nearest_result(ddb_table):
    """Sanity check on the cosine maths through the whole activity."""
    _seed(["deglazing a pan", "blooming spices", "making a roux"])

    result = query_embeddings.run({"query_text": "making a roux", "top_k": 3})

    assert result[0]["source_text"] == "making a roux"
    assert result[0]["distance"] < 1e-9


def test_raw_vectors_are_not_returned(ddb_table):
    """These become Step Functions task output - a 1024-float array per row would
    eat the state payload budget for no benefit."""
    _seed(["a", "b"])

    result = query_embeddings.run({"query_text": "x", "top_k": 2})

    assert all("embedding" not in item for item in result)
    assert set(result[0]) == {"embedding_id", "source_text", "cuisine_type", "distance"}


def test_empty_corpus_returns_empty_list(ddb_table):
    assert query_embeddings.run({"query_text": "anything", "top_k": 5}) == []


def test_top_k_defaults_from_config(ddb_table, monkeypatch):
    monkeypatch.setenv("VECTOR_SEARCH_TOP_K", "2")
    _seed(["a", "b", "c", "d"])

    result = query_embeddings.run({"query_text": "x"})

    assert len(result) == 2


def test_stub_query_embedding_is_deterministic_for_same_text():
    first = models.pseudo_embedding("roux")
    second = models.pseudo_embedding("roux")

    assert first == second
    assert len(first) == models.EMBEDDING_DIM
