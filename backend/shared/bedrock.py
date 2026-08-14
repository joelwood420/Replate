"""Amazon Bedrock model calls, via the Converse API.

Converse rather than InvokeModel because it normalises the request and response
shape across model families - swapping the Claude model id for a different one
does not change this file.

No API key anywhere: the Lambda's execution role authorises the call. That was
the point of choosing Bedrock (docs/decisions.md, 2026-08-14), and it is why
there is no `is_configured()` check for credentials here - only for whether a
model id has been set.
"""

import json
import threading

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from shared import config as app_config

_lock = threading.Lock()
_client = None


class BedrockError(Exception):
    """A model call failed in a way the caller is expected to handle."""


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                kwargs = {
                    "region_name": app_config.aws_region(),
                    "config": Config(
                        # Model calls are slow; the default 60s socket timeout would
                        # cut off a long generation mid-stream.
                        read_timeout=300,
                        connect_timeout=10,
                        retries={"max_attempts": 1, "mode": "standard"},
                    ),
                }
                endpoint = app_config.aws_endpoint_url()
                if endpoint:
                    kwargs["endpoint_url"] = endpoint
                _client = boto3.client("bedrock-runtime", **kwargs)
    return _client


def reset_client_cache() -> None:
    global _client
    with _lock:
        _client = None


def converse(model_id: str, messages: list[dict], system: str | None = None,
             max_tokens: int = 4096, temperature: float = 0.0) -> str:
    """Send a Converse request and return the assistant's text.

    `messages` uses the Converse shape: `[{"role": "user", "content": [{"text": ...}]}]`.
    Temperature defaults to 0 because every call in this pipeline wants a
    structured, reproducible answer rather than a creative one.
    """
    if not model_id:
        raise BedrockError("no Bedrock model id configured for this call")

    request = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        request["system"] = [{"text": system}]

    try:
        response = get_client().converse(**request)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        # AccessDeniedException here almost always means model access was never
        # granted in the Bedrock console for this model in this region - a manual
        # step CloudFormation cannot perform, so it is worth naming.
        raise BedrockError(f"Bedrock {code}: {exc}") from exc
    except BotoCoreError as exc:
        raise BedrockError(f"{type(exc).__name__}: {exc}") from exc

    blocks = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(block.get("text", "") for block in blocks).strip()
    if not text:
        raise BedrockError("Bedrock returned no text content")
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


def embed(text: str, model_id: str | None = None) -> list[float]:
    """Produce an embedding vector.

    Titan Text Embeddings V2 uses InvokeModel rather than Converse - Converse is
    for chat models only. Kept here so callers have one Bedrock entry point.
    """
    model_id = model_id or app_config.bedrock_embedding_model_id()
    if not model_id:
        raise BedrockError("BEDROCK_EMBEDDING_MODEL_ID is not set")

    try:
        response = get_client().invoke_model(
            modelId=model_id,
            body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
        )
        payload = json.loads(response["body"].read())
    except (ClientError, BotoCoreError) as exc:
        raise BedrockError(f"embedding call failed: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise BedrockError(f"unparseable embedding response: {exc}") from exc

    vector = payload.get("embedding")
    if not isinstance(vector, list):
        raise BedrockError("embedding response missing 'embedding' list")
    return vector
