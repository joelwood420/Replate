import uuid

import pytest

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "CulinaryEmbeddings",
    "DishElements",
    "ElementIngredients",
    "ElementSteps",
    "JobRestaurantCandidates",
    "JobResults",
    "Jobs",
    "MenuItems",
    "Restaurants",
    "Users",
}


def test_can_connect_and_query_version(sql_connection):
    cursor = sql_connection.cursor()
    cursor.execute("SELECT @@VERSION;")
    version = cursor.fetchone()[0]

    assert "Microsoft SQL Server" in version


def test_all_expected_tables_exist(sql_connection):
    cursor = sql_connection.cursor()
    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES;")
    table_names = {row[0] for row in cursor.fetchall()}

    assert EXPECTED_TABLES.issubset(table_names)


def test_insert_and_select_job_round_trip(sql_connection):
    cursor = sql_connection.cursor()
    user_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    cursor.execute("INSERT INTO Users (UserId, Email) VALUES (?, ?)", user_id, "integration@example.com")
    cursor.execute(
        "INSERT INTO Jobs (JobId, UserId, Status, ImageBlobUrl, Latitude, Longitude) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        job_id,
        user_id,
        "Queued",
        "https://example.com/photo.jpg",
        40.7128,
        -74.0060,
    )
    sql_connection.commit()

    cursor.execute("SELECT Status FROM Jobs WHERE JobId = ?", job_id)
    row = cursor.fetchone()

    assert row[0] == "Queued"

    cursor.execute("DELETE FROM Jobs WHERE JobId = ?", job_id)
    cursor.execute("DELETE FROM Users WHERE UserId = ?", user_id)
    sql_connection.commit()
