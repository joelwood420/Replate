from shared import config, models, repository, vectors


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


def build_query_text(match_result: dict | None, vision_guess: dict | None) -> str:
    """The matched menu item's name, falling back to the vision model's guess.

    Lives here rather than in the state machine because ASL has no way to express
    "this or that if the first is empty" - and the fallback matters: a vision-only
    outcome has no matched dish name at all.
    """
    match_result = match_result or {}
    vision_guess = vision_guess or {}
    return match_result.get("dish_name") or vision_guess.get("dish_name_guess") or ""


def handler(event, context=None):
    """Lambda entry point for the QueryCulinaryEmbeddings task."""
    return run(
        {
            "query_text": build_query_text(event.get("match_result"), event.get("vision_guess")),
            "top_k": event.get("top_k"),
        }
    )
