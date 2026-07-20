from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

EMBEDDING_DIM = 1536


class MatchMethod:
    MENU_MATCHED = "menu_matched"
    VISION_ONLY_MEDIUM = "vision_only_medium"
    VISION_ONLY_LOW = "vision_only_low"


class JobStatus:
    QUEUED = "Queued"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"


@dataclass
class DishElementGuess:
    name: str
    description: str
    confidence: float


@dataclass
class VisionGuess:
    dish_name_guess: str
    cuisine_guess: str
    elements: list[DishElementGuess] = field(default_factory=list)


@dataclass
class RestaurantCandidate:
    restaurant_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_m: int
    menu_source_url: str


@dataclass
class MenuItem:
    menu_item_id: str
    item_name: str
    item_description: str
    price: str | None = None


def pseudo_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic stand-in for a real embedding-model call.

    Hashes `text` into a repeatable stream of floats in [-1, 1] so distance
    ordering between texts is stable without calling a real embedding API.
    Not semantically meaningful - swap for a real embedding call in Phase 3.
    """
    values: list[float] = []
    counter = 0
    while len(values) < dim:
        digest = hashlib.sha256(f"{text}:{counter}".encode("utf-8")).digest()
        for i in range(0, len(digest), 4):
            if len(values) >= dim:
                break
            chunk = digest[i : i + 4]
            if len(chunk) < 4:
                continue
            (as_uint,) = struct.unpack(">I", chunk)
            values.append((as_uint / 0xFFFFFFFF) * 2 - 1)
        counter += 1
    return values
