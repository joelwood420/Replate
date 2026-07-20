import copy
import uuid
from datetime import datetime, timedelta, timezone

import azure.durable_functions as df

from shared import config, db

bp = df.Blueprint()

CANNED_MENUS = {
    "stub-1": [
        {
            "item_name": "Margherita Pizza",
            "item_description": "Wood-fired pizza with tomato, mozzarella, and basil",
            "price": "14.00",
        },
        {
            "item_name": "Spaghetti Carbonara",
            "item_description": "Pasta with egg, pecorino, guanciale, and black pepper",
            "price": "16.00",
        },
        {
            "item_name": "Tiramisu",
            "item_description": "Espresso-soaked ladyfingers with mascarpone cream",
            "price": "8.00",
        },
        {
            "item_name": "Caprese Salad",
            "item_description": "Fresh mozzarella, tomato, and basil with olive oil",
            "price": "10.00",
        },
    ],
    "stub-2": [
        {
            "item_name": "Pad Thai",
            "item_description": "Stir-fried rice noodles with tamarind, egg, and peanuts",
            "price": "13.00",
        },
        {
            "item_name": "Green Curry",
            "item_description": "Coconut curry with Thai basil and vegetables",
            "price": "14.00",
        },
        {
            "item_name": "Tom Yum Soup",
            "item_description": "Hot and sour soup with lemongrass and shrimp",
            "price": "9.00",
        },
        {
            "item_name": "Mango Sticky Rice",
            "item_description": "Sweet sticky rice with fresh mango and coconut milk",
            "price": "7.00",
        },
    ],
    "stub-3": [
        {
            "item_name": "Cheeseburger",
            "item_description": "Grilled beef patty with cheddar, lettuce, and tomato on a brioche bun",
            "price": "12.00",
        },
        {
            "item_name": "Loaded Fries",
            "item_description": "Fries topped with cheese, bacon, and scallions",
            "price": "8.00",
        },
        {
            "item_name": "Chicken Sandwich",
            "item_description": "Crispy fried chicken with pickles and mayo",
            "price": "11.00",
        },
        {"item_name": "Milkshake", "item_description": "Classic vanilla milkshake", "price": "5.00"},
    ],
}


def _stub_fetch(restaurant_id: str) -> list[dict]:
    return copy.deepcopy(CANNED_MENUS.get(restaurant_id, []))


def _execute(activity_input: dict, conn) -> dict:
    restaurant_id = activity_input["restaurant_id"]
    menu_source_url = activity_input.get("menu_source_url")
    cursor = conn.cursor()

    cursor.execute("SELECT MenuLastFetchedAt FROM Restaurants WHERE RestaurantId = ?", restaurant_id)
    row = cursor.fetchone()
    last_fetched = row[0] if row else None

    if last_fetched is not None:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=config.menu_cache_ttl_hours())
        if last_fetched > cutoff:
            cursor.execute(
                "SELECT MenuItemId, ItemName, ItemDescription, Price FROM MenuItems WHERE RestaurantId = ?",
                restaurant_id,
            )
            cached_rows = cursor.fetchall()
            if cached_rows:
                items = [
                    {
                        "menu_item_id": str(cached.MenuItemId),
                        "item_name": cached.ItemName,
                        "item_description": cached.ItemDescription,
                        "price": cached.Price,
                    }
                    for cached in cached_rows
                ]
                return {"restaurant_id": restaurant_id, "items": items, "source": "cache"}

    fetched_items = _stub_fetch(restaurant_id)
    cursor.execute("DELETE FROM MenuItems WHERE RestaurantId = ?", restaurant_id)

    persisted_items = []
    for item in fetched_items:
        menu_item_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO MenuItems (MenuItemId, RestaurantId, ItemName, ItemDescription, Price) "
            "VALUES (?, ?, ?, ?, ?)",
            menu_item_id,
            restaurant_id,
            item["item_name"],
            item["item_description"],
            item["price"],
        )
        persisted_items.append({"menu_item_id": menu_item_id, **item})

    cursor.execute(
        "UPDATE Restaurants SET MenuSourceUrl = ?, MenuLastFetchedAt = SYSUTCDATETIME() WHERE RestaurantId = ?",
        menu_source_url,
        restaurant_id,
    )
    return {"restaurant_id": restaurant_id, "items": persisted_items, "source": "stub_fetch"}


def run(activity_input: dict) -> dict:
    with db.get_connection() as conn:
        return _execute(activity_input, conn)


@bp.activity_trigger(input_name="activityInput")
def fetch_restaurant_menu(activityInput: dict) -> dict:
    return run(activityInput)
