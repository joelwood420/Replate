import logging
import os

from dotenv import load_dotenv

# Load a .env only for local dev / tests. In Lambda, AWS_LAMBDA_FUNCTION_NAME is always
# set - and load_dotenv() fills in any *unset* var, so a .env accidentally packaged into
# the function zip would silently reintroduce local config (e.g. AWS_ENDPOINT_URL pointing
# at LocalStack) in production. Gating on the Lambda marker makes that impossible.
if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    load_dotenv()

# AWS Lambda's Python runtime leaves the root logger at WARNING, which silences every
# logging.info in this codebase - including the model usage/timing diagnostics that make
# a scan's cost and latency visible. config is imported by every handler, so raise the
# level here once, at cold start. Override with LOG_LEVEL (e.g. WARNING to quieten it).
logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())


def aws_region() -> str:
    # AWS_REGION is set by the Lambda runtime itself; AWS_DEFAULT_REGION is what
    # the CLI and local tooling use. Falling back across both means the same code
    # runs deployed and against LocalStack without a bespoke setting.
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-2")


def aws_endpoint_url() -> str:
    # Blank in a real deployment - set only to point boto3 at LocalStack or
    # DynamoDB Local. Anything non-empty overrides normal endpoint resolution.
    return os.environ.get("AWS_ENDPOINT_URL", "").strip()


def ddb_table_name() -> str:
    return os.environ.get("DDB_TABLE_NAME", "replate")


def s3_bucket_uploads() -> str:
    return os.environ.get("S3_BUCKET_UPLOADS", "replate-uploads")


def sqs_queue_url() -> str:
    # Set from the SAM template in a deployed environment. Blank locally, where
    # shared/queue.py falls back to creating the queue by name against LocalStack.
    return os.environ.get("SQS_QUEUE_URL", "").strip()


def sqs_queue_name() -> str:
    return os.environ.get("SQS_QUEUE_NAME", "replate-jobs")


def presigned_url_expiry_minutes() -> int:
    return int(os.environ.get("PRESIGNED_URL_EXPIRY_MINUTES", "15"))


def identify_state_machine_arn() -> str:
    return os.environ.get("IDENTIFY_STATE_MACHINE_ARN", "")


def recipe_state_machine_arn() -> str:
    return os.environ.get("RECIPE_STATE_MACHINE_ARN", "")


def menu_cache_ttl_hours() -> int:
    return int(os.environ.get("MENU_CACHE_TTL_HOURS", "24"))


def menu_match_confidence_threshold() -> float:
    return float(os.environ.get("MENU_MATCH_CONFIDENCE_THRESHOLD", "0.6"))


def vector_search_top_k() -> int:
    return int(os.environ.get("VECTOR_SEARCH_TOP_K", "5"))


def stub_auth_header_name() -> str:
    return os.environ.get("STUB_AUTH_HEADER_NAME", "X-Debug-User-Oid")


def stub_default_user_oid() -> str:
    return os.environ.get("STUB_DEFAULT_USER_OID", "00000000-0000-0000-0000-000000000001")


def cognito_enabled() -> bool:
    return os.environ.get("COGNITO_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def places_timeout_seconds() -> float:
    return float(os.environ.get("PLACES_TIMEOUT_SECONDS", "8"))


# --- Anthropic API ------------------------------------------------------------------
# First-party Anthropic API (docs/decisions.md, 2026-08-17). Unlike Bedrock this
# needs a stored API key - ANTHROPIC_API_KEY, held in Parameter Store as a
# SecureString when deployed and blank locally. A blank key degrades gracefully
# (menu fetch falls back to the vision-only outcome) rather than crashing.


def anthropic_api_key() -> str:
    # Local dev / tests set the key directly; deployed, it comes from SSM via
    # anthropic_api_key_param() (see anthropic_client._resolved_key).
    return os.environ.get("ANTHROPIC_API_KEY", "")


def anthropic_api_key_param() -> str:
    # SSM SecureString parameter name (e.g. /replate/anthropic-api-key). Set by the
    # SAM template when deployed; blank locally, where the plain env var is used.
    return os.environ.get("ANTHROPIC_API_KEY_PARAM", "").strip()


def anthropic_menu_model() -> str:
    # Default supports the web_search_20260209 server tool (Sonnet 4.6+/Opus 4.6+);
    # Haiku 4.5 only has the basic web_search variant.
    return os.environ.get("ANTHROPIC_MENU_MODEL", "claude-sonnet-5")


def anthropic_vision_model() -> str:
    # Placeholder for Phase 3b - vision_guess is still a stub.
    return os.environ.get("ANTHROPIC_VISION_MODEL", "")


def anthropic_generator_model() -> str:
    # Placeholder for Phase 3b - generate_recreation is still a stub.
    return os.environ.get("ANTHROPIC_GENERATOR_MODEL", "")


def anthropic_timeout_seconds() -> float:
    return float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "120"))


def web_search_timeout_seconds() -> float:
    # Wall-clock budget for a whole menu web_search (its pause-turn resumes included).
    # MUST stay below the fetch-menu Lambda timeout (120s) so a slow or looping search
    # fails as an AnthropicError - which the caller degrades to the vision-only outcome,
    # keeping the scan alive - instead of the Lambda being killed and the job marked
    # Failed. Equal timeouts were why slow menus failed whole scans (see the 2026-08-24
    # incident: fetch-menu hit Sandbox.Timedout at 120.00s, twice).
    return float(os.environ.get("WEB_SEARCH_TIMEOUT_SECONDS", "75"))


def web_search_max_uses() -> int:
    # How many times the model may call the server-side web_search tool in a single
    # menu fetch. Each search costs money and pulls the read page into context (billed
    # as input on every following turn), so this is a direct cost lever. Finding one
    # restaurant's menu rarely needs more than 2-3 searches; the old ceiling of 5,
    # multiplied by a re-searching retry loop, was how one dish once cost 15 searches.
    return int(os.environ.get("WEB_SEARCH_MAX_USES", "3"))


def rate_limit_enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() in ("1", "true", "yes")


def scan_rate_limit_per_hour() -> int:
    return int(os.environ.get("SCAN_RATE_LIMIT_PER_HOUR", "10"))


def scan_rate_limit_per_day() -> int:
    return int(os.environ.get("SCAN_RATE_LIMIT_PER_DAY", "30"))


def recipe_rate_limit_per_hour() -> int:
    return int(os.environ.get("RECIPE_RATE_LIMIT_PER_HOUR", "5"))


def recipe_rate_limit_per_day() -> int:
    return int(os.environ.get("RECIPE_RATE_LIMIT_PER_DAY", "15"))


def moderation_enabled() -> bool:
    # Off by default locally. There is no key to leave blank any more - Rekognition
    # authenticates by IAM - so this flag is what "no moderation configured" became,
    # and shared/moderation.py reports it as unchecked rather than raising.
    return os.environ.get("MODERATION_ENABLED", "false").strip().lower() in ("1", "true", "yes")


def moderation_min_confidence() -> float:
    # Rekognition scores each label 0-100 rather than Azure's 0/2/4/6 severity scale.
    # 80 is deliberately high: a food photo reading low on a category should not fail
    # a scan, and the false-positive cost here is a user who cannot use the app.
    return float(os.environ.get("MODERATION_MIN_CONFIDENCE", "80"))


def moderation_max_retries() -> int:
    return int(os.environ.get("MODERATION_MAX_RETRIES", "2"))
