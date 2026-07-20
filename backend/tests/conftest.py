import pytest


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
