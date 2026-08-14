import pytest

from moto import mock_aws

from shared import ddb


@pytest.fixture
def ddb_table(monkeypatch):
    """An in-process DynamoDB table, via moto.

    The SQL-era unit tests stubbed a pyodbc cursor and asserted on the SQL text
    that reached it. That could not catch a column typo, and it meant the tests
    described the query rather than the behaviour. moto runs a real enough
    DynamoDB in-process - condition expressions, update expressions, sort-key
    ranges and all - so these tests now exercise `shared/repository.py` for real
    while staying fast and needing no Docker.

    Credentials are dummies and AWS_ENDPOINT_URL is cleared: moto intercepts
    botocore itself, so a leftover LocalStack endpoint in the developer's .env
    would bypass the mock and try to reach the network.
    """
    for name, value in (
        ("AWS_ACCESS_KEY_ID", "testing"),
        ("AWS_SECRET_ACCESS_KEY", "testing"),
        ("AWS_SECURITY_TOKEN", "testing"),
        ("AWS_SESSION_TOKEN", "testing"),
        ("AWS_DEFAULT_REGION", "eu-west-2"),
        ("AWS_ENDPOINT_URL", ""),
        ("DDB_TABLE_NAME", "replate-test"),
    ):
        monkeypatch.setenv(name, value)

    ddb.reset_table_cache()
    with mock_aws():
        client = ddb.client()
        client.create_table(
            TableName="replate-test",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield ddb.get_table()
    ddb.reset_table_cache()


@pytest.fixture
def sample_vision_guess():
    return {
        "dish_name_guess": "Margherita Pizza",
        "cuisine_guess": "Italian",
        "elements": [
            {"name": "Pizza crust", "description": "Thin, charred wood-fired crust", "confidence": 0.82},
            {"name": "Tomato sauce", "description": "Simple crushed tomato sauce", "confidence": 0.78},
            {"name": "Mozzarella", "description": "Fresh mozzarella, melted", "confidence": 0.88},
        ],
    }


@pytest.fixture
def sample_menu_items():
    return [
        {
            "menu_item_id": "item-1",
            "item_name": "Margherita Pizza",
            "item_description": "Wood-fired pizza with tomato, mozzarella, and basil",
            "price": "14.00",
        },
        {
            "menu_item_id": "item-2",
            "item_name": "Spaghetti Carbonara",
            "item_description": "Pasta with egg, pecorino, guanciale, and black pepper",
            "price": "16.00",
        },
    ]
