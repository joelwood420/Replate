import copy
import hashlib


CANNED_GUESSES = [
    {
        "dish_name_guess": "Margherita Pizza",
        "cuisine_guess": "Italian",
        "elements": [
            {"name": "Pizza crust", "description": "Thin, charred wood-fired crust", "confidence": 0.82},
            {"name": "Tomato sauce", "description": "Simple crushed tomato sauce", "confidence": 0.78},
            {"name": "Mozzarella", "description": "Fresh mozzarella, melted", "confidence": 0.88},
            {"name": "Basil", "description": "Fresh basil leaves", "confidence": 0.70},
        ],
    },
    {
        "dish_name_guess": "Pad Thai",
        "cuisine_guess": "Thai",
        "elements": [
            {"name": "Rice noodles", "description": "Stir-fried flat rice noodles", "confidence": 0.80},
            {"name": "Tamarind sauce", "description": "Sweet-sour tamarind glaze", "confidence": 0.65},
            {"name": "Peanuts", "description": "Crushed roasted peanuts garnish", "confidence": 0.75},
            {"name": "Egg", "description": "Scrambled egg mixed through", "confidence": 0.60},
        ],
    },
    {
        "dish_name_guess": "Cheeseburger",
        "cuisine_guess": "American",
        "elements": [
            {"name": "Beef patty", "description": "Grilled ground beef patty", "confidence": 0.90},
            {"name": "Cheese", "description": "Melted cheddar slice", "confidence": 0.85},
            {"name": "Bun", "description": "Toasted brioche bun", "confidence": 0.77},
            {"name": "Lettuce & tomato", "description": "Fresh lettuce and tomato slice", "confidence": 0.60},
        ],
    },
]


def run(activity_input: dict) -> dict:
    image_key = activity_input.get("image_key") or ""
    digest = hashlib.sha256(image_key.encode("utf-8")).digest()
    index = digest[0] % len(CANNED_GUESSES)
    return copy.deepcopy(CANNED_GUESSES[index])


def handler(event, context=None):
    """Lambda entry point for the VisionGuess task in statemachines/dish-identify.asl.json."""
    return run(event)
