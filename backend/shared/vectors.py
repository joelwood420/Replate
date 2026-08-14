"""In-process vector similarity, replacing Azure SQL's `VECTOR_DISTANCE`.

The culinary-technique corpus is a few hundred rows and the Azure design was
already scanning all of it with no index (DiskANN being private preview at the
time). So this is the same brute-force cosine comparison it always was - it just
runs in the Lambda now instead of the database.

Distances are returned as **cosine distance** (`1 - cosine similarity`, so lower
is closer), matching what `VECTOR_DISTANCE('cosine', ...)` returned. Keeping the
sign convention means the activity's output contract is unchanged.

If this ever stops being trivially cheap, that is the signal to add a real vector
index - not to micro-optimise this file.
"""

import numpy as np


def cosine_distances(query: list[float], matrix: np.ndarray) -> np.ndarray:
    """Cosine distance from `query` to every row of `matrix`.

    Zero-norm rows would divide by zero; they are clamped to 1.0 so they score as
    maximally distant rather than producing NaN and poisoning the sort.
    """
    query_vector = np.asarray(query, dtype=np.float64)
    query_norm = np.linalg.norm(query_vector)
    row_norms = np.linalg.norm(matrix, axis=1)

    denominator = row_norms * query_norm
    similarities = np.zeros(matrix.shape[0], dtype=np.float64)
    usable = denominator > 0
    similarities[usable] = (matrix[usable] @ query_vector) / denominator[usable]

    return 1.0 - similarities


def top_k(query: list[float], candidates: list[dict], k: int,
          vector_key: str = "embedding") -> list[dict]:
    """Return the `k` closest candidates, nearest first.

    Each result is the candidate dict without its raw vector, plus a `distance`.
    Dropping the vector matters: these results are handed to Step Functions as
    task output, and a 1024-float array per row would eat the state payload limit
    for no benefit.
    """
    if not candidates or k <= 0:
        return []

    matrix = np.array([candidate[vector_key] for candidate in candidates], dtype=np.float64)
    distances = cosine_distances(query, matrix)

    # argsort over the whole array is fine at this size; argpartition would save
    # nothing measurable on a few hundred rows and reads worse.
    order = np.argsort(distances)[:k]

    results = []
    for index in order:
        candidate = {key: value for key, value in candidates[index].items() if key != vector_key}
        candidate["distance"] = float(distances[index])
        results.append(candidate)
    return results
