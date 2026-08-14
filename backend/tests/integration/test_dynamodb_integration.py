"""Data-layer round trips against a real DynamoDB endpoint.

Replaces the SQL Server integration suite. The old tests checked that eleven
tables existed; there is one table now and its shape is trivial, so what is worth
verifying moved to the layer above: that the key conventions in `shared/ddb.py`
actually produce the access patterns `shared/repository.py` claims they do.
"""

import pytest

from shared import ddb, repository
from shared.models import JobStatus

pytestmark = pytest.mark.integration


def test_table_exists_with_composite_key(ddb_table):
    key_schema = {entry["AttributeName"]: entry["KeyType"] for entry in ddb_table.key_schema}

    assert key_schema == {"PK": "HASH", "SK": "RANGE"}


def test_job_round_trip(ddb_table, unique_user_oid):
    job_id = "job-round-trip"
    repository.create_job(
        job_id=job_id,
        user_oid=unique_user_oid,
        status=JobStatus.QUEUED,
        image_key="uploads/photo.jpg",
        latitude=40.7128,
        longitude=-74.0060,
    )

    job = repository.get_job(job_id)

    assert job["status"] == JobStatus.QUEUED
    assert job["user_id"] == unique_user_oid
    # Floats survive the Decimal round trip as floats, not Decimals - a Decimal
    # leaking out would blow up json.dumps in the HTTP layer.
    assert isinstance(job["latitude"], float)
    assert job["latitude"] == pytest.approx(40.7128)


def test_jobs_list_returns_newest_first(ddb_table, unique_user_oid):
    for index in range(3):
        repository.create_job(
            job_id=f"job-order-{index}",
            user_oid=unique_user_oid,
            status=JobStatus.QUEUED,
            image_key=f"uploads/{index}.jpg",
        )

    jobs = repository.list_jobs(unique_user_oid)

    # Descending by the ISO timestamp embedded in the sort key - this is what
    # replaced ORDER BY CreatedAt DESC and its index.
    assert [job["job_id"] for job in jobs] == ["job-order-2", "job-order-1", "job-order-0"]


def test_status_change_propagates_to_the_listing_projection(ddb_table, unique_user_oid):
    job_id = "job-projection"
    repository.create_job(
        job_id=job_id, user_oid=unique_user_oid, status=JobStatus.QUEUED, image_key="uploads/p.jpg"
    )

    repository.update_job(
        job_id, status=JobStatus.IDENTIFIED, is_saved=True, dish_name="Margherita Pizza"
    )

    listed = repository.list_jobs(unique_user_oid)[0]
    canonical = repository.get_job(job_id)

    # The denormalisation is only safe if these two never disagree.
    assert listed["status"] == canonical["status"] == JobStatus.IDENTIFIED
    assert listed["is_saved"] is True
    assert listed["dish_name"] == "Margherita Pizza"


def test_saved_filter_narrows_the_listing(ddb_table, unique_user_oid):
    repository.create_job(
        job_id="job-saved", user_oid=unique_user_oid, status=JobStatus.QUEUED, image_key="a.jpg"
    )
    repository.create_job(
        job_id="job-unsaved", user_oid=unique_user_oid, status=JobStatus.QUEUED, image_key="b.jpg"
    )
    repository.update_job("job-saved", is_saved=True)

    saved = repository.list_jobs(unique_user_oid, saved=True)
    unsaved = repository.list_jobs(unique_user_oid, saved=False)

    assert [job["job_id"] for job in saved] == ["job-saved"]
    assert [job["job_id"] for job in unsaved] == ["job-unsaved"]


def test_elements_round_trip_with_nested_ingredients_and_steps(ddb_table):
    job_id = "job-elements"
    repository.replace_dish_elements(
        job_id,
        [
            {
                "name": "Pizza base",
                "description": "Thin, charred",
                "role": "base",
                "sort_order": 0,
                "ingredients": [
                    {"ingredient_name": "00 flour", "amount": "500", "unit": "g", "sort_order": 0},
                    {"ingredient_name": "Water", "amount": "325", "unit": "ml", "sort_order": 1},
                ],
                "steps": [
                    {"step_number": 1, "instruction": "Mix and knead."},
                    {"step_number": 2, "instruction": "Prove overnight."},
                ],
            }
        ],
    )

    elements = repository.get_dish_elements(job_id)

    assert len(elements) == 1
    assert [i["ingredient_name"] for i in elements[0]["ingredients"]] == ["00 flour", "Water"]
    assert [s["step_number"] for s in elements[0]["steps"]] == [1, 2]


def test_replacing_elements_does_not_duplicate_them(ddb_table):
    """Re-running generation must replace the recipe, not append to it."""
    job_id = "job-regenerate"
    element = {"name": "Sauce", "sort_order": 0, "ingredients": [], "steps": []}

    repository.replace_dish_elements(job_id, [element])
    repository.replace_dish_elements(job_id, [element])

    assert len(repository.get_dish_elements(job_id)) == 1


def test_elements_sort_numerically_past_ten(ddb_table):
    """Zero-padded sort keys: without the padding ELEMENT#10 sorts before ELEMENT#2."""
    job_id = "job-many-elements"
    repository.replace_dish_elements(
        job_id,
        [
            {"name": f"Element {i}", "sort_order": i, "ingredients": [], "steps": []}
            for i in range(12)
        ],
    )

    elements = repository.get_dish_elements(job_id)

    assert [element["name"] for element in elements] == [f"Element {i}" for i in range(12)]


def test_upsert_restaurant_does_not_clobber_a_cached_menu(ddb_table):
    """The whole reason upsert is insert-if-absent rather than a blind put."""
    repository.upsert_restaurant("rest-1", "Trattoria", "1 Main St", 1.0, 2.0, "https://menu")
    repository.mark_menu_fetched("rest-1", "https://menu")

    repository.upsert_restaurant("rest-1", "Trattoria", "1 Main St", 1.0, 2.0, None)

    restaurant = repository.get_restaurant("rest-1")
    assert restaurant["menu_last_fetched_at"] is not None


def test_menu_items_replaced_wholesale(ddb_table):
    repository.replace_menu_items("rest-2", [{"item_name": "Old", "item_description": None, "price": None}])
    persisted = repository.replace_menu_items(
        "rest-2", [{"item_name": "New", "item_description": "d", "price": "9.00"}]
    )

    items = repository.get_menu_items("rest-2")

    assert [item["item_name"] for item in items] == ["New"]
    assert persisted[0]["menu_item_id"] == items[0]["menu_item_id"]


def test_strip_keys_removes_the_composite_key(ddb_table, unique_user_oid):
    repository.create_job(
        job_id="job-keys", user_oid=unique_user_oid, status=JobStatus.QUEUED, image_key="k.jpg"
    )

    job = repository.get_job("job-keys")

    # PK/SK are this layer's business and must not leak into API payloads.
    assert "PK" not in job and "SK" not in job
    raw = ddb.get(ddb.job_pk("job-keys"), ddb.SK_META)
    assert raw["PK"] == "JOB#job-keys"
