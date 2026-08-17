"""First-party Anthropic API model calls, via the Messages API.

Replaces the Amazon Bedrock wrapper (docs/decisions.md, 2026-08-17). Bedrock
authenticated by the Lambda execution role and had no server-side web_search
tool; the first-party API needs an API key but *does* expose web_search, which
is why fetch_restaurant_menu can go back to a single search+fetch+extract call.

The API key is read from ANTHROPIC_API_KEY (Parameter Store SecureString when
deployed, blank locally). `is_configured()` is the stub gate: with no key,
callers degrade instead of crashing - the same posture the blank Bedrock model
id had before.
"""

import json
import threading

import anthropic

from shared import config as app_config

_lock = threading.Lock()
_client = None

# Bound how many times the model may invoke the server-side web_search tool in a
# single menu fetch - a cost and latency ceiling on one call.
WEB_SEARCH_MAX_USES = 5

# The model can pause a long server-tool turn (stop_reason == "pause_turn") and
# expects to be re-sent to resume. Cap the resumes so a misbehaving turn cannot
# loop forever.
_MAX_PAUSE_RESUMES = 5


class AnthropicError(Exception):
    """A model call failed in a way the caller is expected to handle."""


def is_configured() -> bool:
    return bool(app_config.anthropic_api_key())


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = anthropic.Anthropic(
                    api_key=app_config.anthropic_api_key(),
                    # Model calls with a web_search loop are slow; the default
                    # 10-minute client timeout is generous enough, but pin it so
                    # a hung request cannot outlive the Lambda.
                    timeout=app_config.anthropic_timeout_seconds(),
                    max_retries=1,
                )
    return _client


def reset_client_cache() -> None:
    global _client
    with _lock:
        _client = None


def _collect_text(content) -> str:
    """Join the text blocks of a response's content, ignoring tool blocks."""
    return "".join(
        block.text for block in content if getattr(block, "type", None) == "text"
    ).strip()


def web_search_completion(
    model: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Run a Messages call with the server-side web_search tool and return text.

    `messages` uses the Messages API shape:
    `[{"role": "user", "content": [{"type": "text", "text": ...}]}]`. The model
    searches and reads pages on its own, so no page text is passed in. A
    `pause_turn` stop reason is resumed automatically, bounded by
    `_MAX_PAUSE_RESUMES`.
    """
    if not is_configured():
        raise AnthropicError("ANTHROPIC_API_KEY is not set")
    if not model:
        raise AnthropicError("no Anthropic model id configured for this call")

    request = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": list(messages),
        "tools": [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": WEB_SEARCH_MAX_USES,
            }
        ],
    }
    if system:
        request["system"] = system

    client = get_client()
    try:
        response = client.messages.create(**request)
        # Resume the server-tool loop if the turn paused mid-search.
        resumes = 0
        while response.stop_reason == "pause_turn" and resumes < _MAX_PAUSE_RESUMES:
            request["messages"] = request["messages"] + [
                {"role": "assistant", "content": response.content}
            ]
            response = client.messages.create(**request)
            resumes += 1
    except (anthropic.APIError, anthropic.APIConnectionError) as exc:
        # AuthenticationError / PermissionDeniedError here almost always mean a
        # missing or wrong ANTHROPIC_API_KEY, or a key without model access.
        raise AnthropicError(f"{type(exc).__name__}: {exc}") from exc

    text = _collect_text(response.content)
    if not text:
        raise AnthropicError("Anthropic returned no text content")
    return text


def parse_json_response(raw: str) -> dict:
    """Parse a model's JSON reply, tolerating a markdown code fence around it.

    Models wrap JSON in ```json fences often enough that stripping them is not
    worth a retry round-trip.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)
