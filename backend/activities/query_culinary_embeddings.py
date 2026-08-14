import azure.durable_functions as df

from shared import config, models, repository, vectors

bp = df.Blueprint()


def run(activity_input: dict) -> list[dict]:
    """Retrieve the culinary techniques closest to the dish description.

    Was a `SELECT TOP (k) ... ORDER BY VECTOR_DISTANCE(...)` against Azure SQL.
    Now the whole (small) corpus is read and compared in-process - see
    `shared/vectors.py` for why that is the same amount of work it always was.
    """
    query_text = activity_input.get("query_text") or ""
    top_k = activity_input.get("top_k") or config.vector_search_top_k()

    candidates = repository.all_embeddings()
    if not candidates:
        return []

    query_vector = models.pseudo_embedding(query_text)
    return vectors.top_k(query_vector, candidates, top_k)


@bp.activity_trigger(input_name="activityInput")
def query_culinary_embeddings(activityInput: dict) -> list[dict]:
    return run(activityInput)
