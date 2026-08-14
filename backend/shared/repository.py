"""Domain data access for Replate, over the single DynamoDB table.

This is the layer that replaced the raw T-SQL scattered across the triggers and
activities. Everything above it works in plain dicts and never sees a key format.

Two shape changes are worth knowing about, because they are genuine
single-table-design decisions rather than mechanical translations:

**Elements are one item, not three tables.** `DishElements`,
`ElementIngredients` and `ElementSteps` were three tables joined on every read.
Here an element is a single item with its ingredients and steps nested as lists.
Reading a recipe went from three queries per element to one query per job.

**The job listing is denormalised.** `GET /api/jobs` used to join Jobs ->
JobResults -> Restaurants to show a dish name and restaurant name per row.
DynamoDB has no joins, so each job also writes a projection item into the
owner's partition (`USER#<oid> / JOB#<ts>#<jobId>`) carrying just what the list
needs. The canonical record stays at `JOB#<jobId> / META`. Every write that
touches a projected field goes through the helpers here, so the two cannot drift
apart - that is the cost of the denormalisation and the reason these functions
exist rather than callers writing items directly.
"""

import datetime
import uuid

from shared import ddb

# Fields duplicated from the canonical job/result items onto the user's listing
# projection. Kept as a named set so it is obvious what has to be maintained in
# two places, and so `_sync_projection` cannot silently miss one.
PROJECTED_FIELDS = ("status", "is_saved", "dish_name", "restaurant_name")


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with an explicit offset.

    The offset is not optional. The SQL version stored naive DATETIME2 and had to
    re-attach UTC on the way out (`db.to_utc_iso`), because `new Date(...)` on the
    client parses an offset-less string as local time and skews every "time ago"
    display by the viewer's timezone. Storing the offset removes that whole class
    of bug - and ISO-8601 UTC sorts lexicographically, which is what makes the
    job sort key work.
    """
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------


def ensure_user(user_oid: str, email: str | None = None, display_name: str | None = None) -> None:
    """Create the user's profile item if it doesn't exist yet.

    Insert-if-absent, so a returning user's email/display name are not
    overwritten with whatever the current token happens to carry.
    """
    ddb.put_if_absent(
        {
            "PK": ddb.user_pk(user_oid),
            "SK": ddb.SK_PROFILE,
            "user_id": user_oid,
            "email": email,
            "display_name": display_name,
            "created_at": utc_now_iso(),
        }
    )


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


def create_job(
    job_id: str,
    user_oid: str,
    status: str,
    image_key: str,
    latitude: float | None = None,
    longitude: float | None = None,
    selected_restaurant_id: str | None = None,
) -> dict:
    """Write the canonical job item and its listing projection."""
    created_at = utc_now_iso()
    job = {
        "PK": ddb.job_pk(job_id),
        "SK": ddb.SK_META,
        "job_id": job_id,
        "user_id": user_oid,
        "status": status,
        "image_key": image_key,
        "latitude": latitude,
        "longitude": longitude,
        "selected_restaurant_id": selected_restaurant_id,
        "error_message": None,
        "is_saved": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    ddb.put(job)
    ddb.put(
        {
            "PK": ddb.user_pk(user_oid),
            "SK": ddb.job_index_sk(created_at, job_id),
            "job_id": job_id,
            "status": status,
            "is_saved": False,
            "created_at": created_at,
            "image_key": image_key,
            "dish_name": None,
            "restaurant_name": None,
        }
    )
    return ddb.strip_keys(job)


def get_job(job_id: str) -> dict | None:
    item = ddb.get(ddb.job_pk(job_id), ddb.SK_META)
    return ddb.strip_keys(item) if item else None


def _sync_projection(job: dict, changes: dict) -> None:
    """Mirror projected fields onto the owner's listing item."""
    projected = {k: v for k, v in changes.items() if k in PROJECTED_FIELDS}
    if not projected:
        return
    ddb.update(
        ddb.user_pk(job["user_id"]),
        ddb.job_index_sk(job["created_at"], job["job_id"]),
        projected,
    )


def update_job(job_id: str, **changes) -> dict | None:
    """Apply changes to a job, keeping `updated_at` and the projection in step.

    Returns None if the job doesn't exist. Pass `error_message=None` explicitly to
    clear a previous error - the distinction between "not mentioned" and
    "explicitly None" is why this takes kwargs rather than optional parameters.
    """
    job = get_job(job_id)
    if job is None:
        return None

    changes["updated_at"] = utc_now_iso()
    updated = ddb.update(ddb.job_pk(job_id), ddb.SK_META, changes)
    _sync_projection(job, changes)
    return ddb.strip_keys(updated) if updated else None


def list_jobs(user_oid: str, saved: bool | None = None, limit: int = 20) -> list[dict]:
    """The cookbook listing - newest first.

    `ascending=False` walks the sort key backwards, which is descending
    chronological order because the key leads with an ISO timestamp. That replaces
    `ORDER BY CreatedAt DESC` and the `IX_Jobs_UserId` index it needed.

    The saved filter is applied after the read rather than as a DynamoDB
    FilterExpression: a filter is evaluated after items are read and still bills
    for them, so at these partition sizes it buys nothing but does make `limit`
    behave unintuitively.
    """
    items = ddb.query_prefix(ddb.user_pk(user_oid), "JOB#", ascending=False)
    if saved is not None:
        items = [item for item in items if bool(item.get("is_saved")) == saved]
    return [ddb.strip_keys(item) for item in items[:limit]]


# --------------------------------------------------------------------------
# Job results
# --------------------------------------------------------------------------


def put_job_result(job_id: str, result: dict, vision_guess: dict | None = None) -> None:
    """Write the stage-1 match result.

    `vision_guess` is persisted alongside it because stage 2 (recipe generation,
    triggered later by the user) takes it as input - before the pipeline was split
    the guess only survived as generated elements.
    """
    ddb.put(
        {
            "PK": ddb.job_pk(job_id),
            "SK": ddb.SK_RESULT,
            "job_id": job_id,
            "dish_name": result.get("dish_name"),
            "cuisine": result.get("cuisine"),
            "confidence": result.get("vision_confidence"),
            "matched_restaurant_id": result.get("matched_restaurant_id"),
            "matched_menu_item_id": result.get("matched_menu_item_id"),
            "match_confidence": result.get("match_confidence"),
            "match_method": result.get("match_method"),
            "vision_guess": vision_guess,
            "created_at": utc_now_iso(),
        }
    )


def get_job_result(job_id: str) -> dict | None:
    item = ddb.get(ddb.job_pk(job_id), ddb.SK_RESULT)
    return ddb.strip_keys(item) if item else None


# --------------------------------------------------------------------------
# Dish elements
# --------------------------------------------------------------------------


def replace_dish_elements(job_id: str, elements: list[dict]) -> None:
    """Replace this job's recipe wholesale.

    Delete-then-write rather than append, so re-running generation after a failed
    or unsatisfying attempt doesn't duplicate every element - the same reason the
    SQL version deleted first.
    """
    ddb.delete_prefix(ddb.job_pk(job_id), "ELEMENT#")

    items = []
    for element in elements:
        sort_order = element["sort_order"]
        items.append(
            {
                "PK": ddb.job_pk(job_id),
                "SK": ddb.element_sk(sort_order),
                "element_id": str(uuid.uuid4()),
                "job_id": job_id,
                "name": element["name"],
                "description": element.get("description"),
                "role": element.get("role"),
                "sort_order": sort_order,
                "ingredients": [
                    {
                        "ingredient_name": ingredient["ingredient_name"],
                        "amount": ingredient.get("amount"),
                        "unit": ingredient.get("unit"),
                        "sort_order": ingredient["sort_order"],
                    }
                    for ingredient in sorted(
                        element.get("ingredients", []), key=lambda i: i["sort_order"]
                    )
                ],
                "steps": [
                    {"step_number": step["step_number"], "instruction": step["instruction"]}
                    for step in sorted(element.get("steps", []), key=lambda s: s["step_number"])
                ],
            }
        )
    ddb.batch_put(items)


def get_dish_elements(job_id: str) -> list[dict]:
    """Read a job's recipe, in element order.

    One query, because ingredients and steps are nested in the element item. The
    sort key is zero-padded so lexicographic order is numeric order.
    """
    items = ddb.query_prefix(ddb.job_pk(job_id), "ELEMENT#")
    return [
        {
            "name": item["name"],
            "description": item.get("description"),
            "role": item.get("role"),
            "ingredients": [
                {
                    "ingredient_name": ingredient["ingredient_name"],
                    "amount": ingredient.get("amount"),
                    "unit": ingredient.get("unit"),
                }
                for ingredient in item.get("ingredients", [])
            ],
            "steps": [
                {"step_number": step["step_number"], "instruction": step["instruction"]}
                for step in item.get("steps", [])
            ],
        }
        for item in items
    ]


# --------------------------------------------------------------------------
# Restaurants and menus
# --------------------------------------------------------------------------


def upsert_restaurant(
    restaurant_id: str,
    name: str,
    address: str | None,
    latitude: float | None,
    longitude: float | None,
    menu_source_url: str | None,
) -> None:
    """Insert a restaurant if absent; never overwrite an existing one.

    See `ddb.put_if_absent` - overwriting would discard a cached menu's
    `MenuLastFetchedAt` and force a re-scrape on every visit.
    """
    ddb.put_if_absent(
        {
            "PK": ddb.restaurant_pk(restaurant_id),
            "SK": ddb.SK_META,
            "restaurant_id": restaurant_id,
            "name": name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "menu_source_url": menu_source_url,
            "menu_last_fetched_at": None,
            "created_at": utc_now_iso(),
        }
    )


def get_restaurant(restaurant_id: str) -> dict | None:
    item = ddb.get(ddb.restaurant_pk(restaurant_id), ddb.SK_META)
    return ddb.strip_keys(item) if item else None


def get_restaurant_name(restaurant_id: str | None) -> str | None:
    """Name lookup for the listing/result payloads, replacing a LEFT JOIN."""
    if not restaurant_id:
        return None
    restaurant = get_restaurant(restaurant_id)
    return restaurant.get("name") if restaurant else None


def replace_menu_items(restaurant_id: str, items: list[dict]) -> list[dict]:
    """Replace a restaurant's cached menu and return the persisted rows."""
    ddb.delete_prefix(ddb.restaurant_pk(restaurant_id), "MENUITEM#")

    persisted = []
    records = []
    for index, item in enumerate(items):
        menu_item_id = str(uuid.uuid4())
        record = {
            "menu_item_id": menu_item_id,
            "item_name": item["item_name"],
            "item_description": item.get("item_description"),
            "price": item.get("price"),
        }
        persisted.append(record)
        records.append(
            {
                "PK": ddb.restaurant_pk(restaurant_id),
                "SK": ddb.menu_item_sk(index),
                "restaurant_id": restaurant_id,
                **record,
            }
        )
    ddb.batch_put(records)
    return persisted


def get_menu_items(restaurant_id: str) -> list[dict]:
    items = ddb.query_prefix(ddb.restaurant_pk(restaurant_id), "MENUITEM#")
    return [
        {
            "menu_item_id": item["menu_item_id"],
            "item_name": item["item_name"],
            "item_description": item.get("item_description"),
            "price": item.get("price"),
        }
        for item in items
    ]


def mark_menu_fetched(restaurant_id: str, menu_source_url: str | None) -> None:
    ddb.update(
        ddb.restaurant_pk(restaurant_id),
        ddb.SK_META,
        {"menu_source_url": menu_source_url, "menu_last_fetched_at": utc_now_iso()},
    )


# --------------------------------------------------------------------------
# Job restaurant candidates
# --------------------------------------------------------------------------


def put_job_candidates(job_id: str, candidates: list[dict]) -> None:
    ddb.batch_put(
        [
            {
                "PK": ddb.job_pk(job_id),
                "SK": ddb.candidate_sk(candidate["restaurant_id"]),
                "job_id": job_id,
                "restaurant_id": candidate["restaurant_id"],
                "distance_m": candidate.get("distance_m"),
            }
            for candidate in candidates
        ]
    )


# --------------------------------------------------------------------------
# Culinary embeddings
# --------------------------------------------------------------------------


def put_embedding(source_text: str, embedding: list[float], cuisine_type: str | None = None,
                  source_url: str | None = None, embedding_id: str | None = None) -> str:
    embedding_id = embedding_id or str(uuid.uuid4())
    ddb.put(
        {
            "PK": ddb.EMBEDDINGS_PK,
            "SK": ddb.technique_sk(embedding_id),
            "embedding_id": embedding_id,
            "source_text": source_text,
            "embedding": embedding,
            "cuisine_type": cuisine_type,
            "source_url": source_url,
            "created_at": utc_now_iso(),
        }
    )
    return embedding_id


def all_embeddings() -> list[dict]:
    """Every culinary-technique vector, for the in-process similarity scan.

    A whole-partition read is deliberate. The corpus is a few hundred rows and the
    Azure design was already doing an unindexed brute-force `VECTOR_DISTANCE` over
    exactly the same data - this just moves the scan from the database into the
    Lambda. If it ever stops being trivially cheap, that is the signal to add a
    real vector index, not to paginate this.
    """
    items = ddb.query_prefix(ddb.EMBEDDINGS_PK, "TECHNIQUE#")
    return [
        {
            "embedding_id": item["embedding_id"],
            "source_text": item["source_text"],
            "cuisine_type": item.get("cuisine_type"),
            "embedding": [float(value) for value in item["embedding"]],
        }
        for item in items
    ]
