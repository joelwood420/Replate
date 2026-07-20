import json

import azure.durable_functions as df

from shared import config, db, models

bp = df.Blueprint()


def _execute(activity_input: dict, conn) -> list[dict]:
    query_text = activity_input.get("query_text") or ""
    top_k = activity_input.get("top_k") or config.vector_search_top_k()
    query_vector_json = json.dumps(models.pseudo_embedding(query_text))

    cursor = conn.cursor()
    cursor.execute(
        "SELECT TOP (?) EmbeddingId, SourceText, CuisineType, "
        "VECTOR_DISTANCE('cosine', Embedding, CAST(CAST(? AS NVARCHAR(MAX)) AS VECTOR(1536))) AS Distance "
        "FROM CulinaryEmbeddings ORDER BY Distance",
        top_k,
        query_vector_json,
    )
    return [
        {
            "embedding_id": str(row.EmbeddingId),
            "source_text": row.SourceText,
            "cuisine_type": row.CuisineType,
            "distance": float(row.Distance),
        }
        for row in cursor.fetchall()
    ]


def run(activity_input: dict) -> list[dict]:
    with db.get_connection() as conn:
        return _execute(activity_input, conn)


@bp.activity_trigger(input_name="activityInput")
def query_culinary_embeddings(activityInput: dict) -> list[dict]:
    return run(activityInput)
