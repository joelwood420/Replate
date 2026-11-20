"""Minimal client for TypeSafe's Jev decision model (POST /v1/systemone).

Jev returns typed answers with probabilities instead of text, in roughly 100 ms, which suits
closed-set decisions such as "which of these menu items is the dish" (docs/decisions.md,
2026-11-21). Only the Choice primitive is wrapped because that is all the pipeline uses.

Plain httpx rather than the `typesafe-sdk` package: httpx is already in the Lambda layer, the
request is one JSON POST, and this keeps the layer free of a second vendor SDK. The key
follows the same pattern as the Anthropic and SerpApi keys: an SSM SecureString when
deployed, a plain env var locally, and any failure to read it degrades to "not configured"
so the caller falls back instead of failing the job.
"""

import logging
import threading

import httpx

from shared import config, secrets

SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"

# One client per Lambda container, so a warm invocation reuses the open TLS connection.
# A fresh connection per call measured ~1.1s from NZ (2026-11-21), most of it handshake.
_client_lock = threading.Lock()
_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client()
    return _client


def reset_client_cache() -> None:
    """Close and drop the shared client - for tests."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None


class TypeSafeError(Exception):
    """A Jev call failed or returned something unusable; the caller should fall back."""


def _resolved_key() -> str:
    param = config.typesafe_api_key_param()
    if param:
        try:
            return secrets.get_secure_parameter(param)
        except Exception as exc:  # noqa: BLE001 - degrade on any SSM failure
            logging.warning("Could not read %s from SSM: %s", param, exc)
            return ""
    return config.typesafe_api_key()


def is_configured() -> bool:
    return bool(config.typesafe_match_model() and _resolved_key())


def choice(state: str, instructions: str, criteria: dict[str, str]) -> tuple[str, float]:
    """Ask Jev one Choice question and return (chosen key, its probability).

    The probability of the chosen option, not Jev's separate `confidence` field, is returned
    because it means "how likely is this the right option", which is what the menu-match
    confidence floor compares against. Raises TypeSafeError on any transport, HTTP or shape
    problem, including a chosen key that is not one of `criteria` (it can never point off
    the list).
    """
    key = _resolved_key()
    if not key:
        raise TypeSafeError("TypeSafe API key is not configured")

    body = {
        "model": config.typesafe_match_model(),
        "state": state,
        "questions": {
            "answer": {"type": "choice", "instructions": instructions, "criteria": criteria},
        },
    }
    try:
        response = get_client().post(
            SYSTEMONE_URL,
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=config.typesafe_timeout_seconds(),
        )
        response.raise_for_status()
        data = response.json()
        answer = data["answers"]["answer"]
        picked = answer["choice"]
        probability = float(answer["probabilities"][picked])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise TypeSafeError(f"Jev choice call failed: {exc}") from exc

    if picked not in criteria:
        raise TypeSafeError(f"Jev returned an option that was not offered: {picked!r}")
    return picked, probability
