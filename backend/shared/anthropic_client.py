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
import logging
import threading

import anthropic

from shared import config as app_config
from shared import secrets

_lock = threading.Lock()
_client = None

# The model can pause a long server-tool turn (stop_reason == "pause_turn") and
# expects to be re-sent to resume. Cap the resumes so a misbehaving turn cannot
# loop forever.
_MAX_PAUSE_RESUMES = 5


class AnthropicError(Exception):
    """A model call failed in a way the caller is expected to handle."""


def _resolved_key() -> str:
    """The Anthropic API key, from SSM when deployed or the env var locally.

    An SSM failure (missing parameter, denied read, service error) degrades to
    the no-key path rather than crashing - the same blank-key posture the stub
    deploy runs on, which the menu-fetch caller already handles as the vision-only
    outcome. Only successful reads are cached, so a transient error is retried.
    """
    param = app_config.anthropic_api_key_param()
    if param:
        try:
            return secrets.get_secure_parameter(param)
        except Exception as exc:  # noqa: BLE001 - degrade on any SSM failure
            logging.warning("Could not read %s from SSM: %s", param, exc)
            return ""
    return app_config.anthropic_api_key()


def is_configured() -> bool:
    return bool(_resolved_key())


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = anthropic.Anthropic(
                    api_key=_resolved_key(),
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


def _log_usage(label: str, response) -> None:
    """Log token and web_search usage for one model turn.

    These calls are the pipeline's dominant cost, so making usage visible per call
    turns a surprise bill into a metric. Web search count lives under
    usage.server_tool_use.web_search_requests when the tool ran; it is absent on
    plain calls. Best-effort: never let logging break a response.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    server_tool_use = getattr(usage, "server_tool_use", None)
    web_searches = getattr(server_tool_use, "web_search_requests", None)
    logging.info(
        "anthropic usage [%s]: input=%s output=%s web_searches=%s",
        label,
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        web_searches,
    )


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
                "max_uses": app_config.web_search_max_uses(),
            }
        ],
    }
    if system:
        request["system"] = system

    client = get_client()
    try:
        response = client.messages.create(**request)
        _log_usage("web_search", response)
        # Resume the server-tool loop if the turn paused mid-search.
        resumes = 0
        while response.stop_reason == "pause_turn" and resumes < _MAX_PAUSE_RESUMES:
            request["messages"] = request["messages"] + [
                {"role": "assistant", "content": response.content}
            ]
            response = client.messages.create(**request)
            _log_usage("web_search:resume", response)
            resumes += 1
    except (anthropic.APIError, anthropic.APIConnectionError) as exc:
        # AuthenticationError / PermissionDeniedError here almost always mean a
        # missing or wrong ANTHROPIC_API_KEY, or a key without model access.
        raise AnthropicError(f"{type(exc).__name__}: {exc}") from exc

    text = _collect_text(response.content)
    if not text:
        raise AnthropicError("Anthropic returned no text content")
    return text


def generate_structured(
    model: str,
    messages: list[dict],
    schema: dict,
    system: str | None = None,
    max_tokens: int = 4096,
    effort: str = "medium",
) -> dict:
    """Run a Messages call constrained to a JSON schema and return parsed JSON.

    Uses `output_config.format` (structured outputs) so the reply validates
    against `schema` - no fragile fenced-JSON parsing, unlike the web_search
    path which cannot use structured outputs alongside a server tool. `effort`
    defaults to medium: this backs the heaviest-output call in the pipeline
    (recipe generation), so thinking depth is bounded deliberately rather than
    left at the `high` default.
    """
    if not is_configured():
        raise AnthropicError("ANTHROPIC_API_KEY is not set")
    if not model:
        raise AnthropicError("no Anthropic model id configured for this call")

    request = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": list(messages),
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": schema},
        },
    }
    if system:
        request["system"] = system

    client = get_client()
    try:
        response = client.messages.create(**request)
        _log_usage("structured", response)
    except (anthropic.APIError, anthropic.APIConnectionError) as exc:
        raise AnthropicError(f"{type(exc).__name__}: {exc}") from exc

    if response.stop_reason == "refusal":
        raise AnthropicError("Anthropic declined the request (stop_reason=refusal)")

    text = _collect_text(response.content)
    if not text:
        raise AnthropicError("Anthropic returned no text content")
    # output_config guarantees valid JSON, but parse_json_response also tolerates
    # a stray fence, costing nothing.
    return parse_json_response(text)


def parse_json_response(raw: str) -> dict:
    """Parse a model's JSON reply, tolerating a markdown code fence around it.

    Models wrap JSON in ```json fences often enough that stripping them is not
    worth a retry round-trip.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)
