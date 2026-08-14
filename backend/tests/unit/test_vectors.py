"""The similarity maths that replaced Azure SQL's VECTOR_DISTANCE.

Pure functions over plain lists, so no table fixture is needed here - the read
path is covered in tests/integration/test_vector_search_integration.py.
"""

import numpy as np
import pytest

from shared import vectors


def _candidates(*rows):
    return [{"id": f"e{i}", "embedding": row} for i, row in enumerate(rows)]


def test_identical_vectors_have_zero_distance():
    distances = vectors.cosine_distances([1.0, 0.0], np.array([[1.0, 0.0]]))

    assert distances[0] == pytest.approx(0.0)


def test_orthogonal_vectors_have_distance_one():
    distances = vectors.cosine_distances([1.0, 0.0], np.array([[0.0, 1.0]]))

    assert distances[0] == pytest.approx(1.0)


def test_opposite_vectors_have_distance_two():
    distances = vectors.cosine_distances([1.0, 0.0], np.array([[-1.0, 0.0]]))

    assert distances[0] == pytest.approx(2.0)


def test_magnitude_does_not_affect_distance():
    """Cosine compares direction - a longer vector in the same direction is
    just as close."""
    distances = vectors.cosine_distances([1.0, 0.0], np.array([[5.0, 0.0]]))

    assert distances[0] == pytest.approx(0.0)


def test_zero_vectors_score_as_maximally_distant_rather_than_nan():
    """A zero norm would divide by zero and poison the sort with NaN."""
    distances = vectors.cosine_distances([1.0, 0.0], np.array([[0.0, 0.0]]))

    assert distances[0] == pytest.approx(1.0)
    assert not np.isnan(distances[0])


def test_a_zero_query_does_not_produce_nan():
    distances = vectors.cosine_distances([0.0, 0.0], np.array([[1.0, 0.0]]))

    assert not np.isnan(distances).any()


def test_top_k_returns_nearest_first():
    candidates = _candidates([0.0, 1.0], [1.0, 0.0], [0.9, 0.1])

    result = vectors.top_k([1.0, 0.0], candidates, 3)

    assert [item["id"] for item in result] == ["e1", "e2", "e0"]
    assert [item["distance"] for item in result] == sorted(item["distance"] for item in result)


def test_top_k_truncates_to_k():
    candidates = _candidates([1.0, 0.0], [0.0, 1.0], [1.0, 1.0])

    assert len(vectors.top_k([1.0, 0.0], candidates, 2)) == 2


def test_top_k_tolerates_k_larger_than_the_corpus():
    candidates = _candidates([1.0, 0.0])

    assert len(vectors.top_k([1.0, 0.0], candidates, 10)) == 1


def test_top_k_strips_the_raw_vector():
    """These become Step Functions task output - a 1024-float array per row would
    eat the state payload budget for no benefit."""
    result = vectors.top_k([1.0, 0.0], _candidates([1.0, 0.0]), 1)

    assert "embedding" not in result[0]
    assert set(result[0]) == {"id", "distance"}


def test_empty_corpus_returns_empty_list():
    assert vectors.top_k([1.0, 0.0], [], 5) == []


def test_zero_k_returns_empty_list():
    assert vectors.top_k([1.0, 0.0], _candidates([1.0, 0.0]), 0) == []
