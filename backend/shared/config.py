import os

from dotenv import load_dotenv

load_dotenv()


def aws_region() -> str:
    # AWS_REGION is set by the Lambda runtime itself; AWS_DEFAULT_REGION is what
    # the CLI and local tooling use. Falling back across both means the same code
    # runs deployed and against LocalStack without a bespoke setting.
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "eu-west-2")


def aws_endpoint_url() -> str:
    # Blank in a real deployment - set only to point boto3 at LocalStack or
    # DynamoDB Local. Anything non-empty overrides normal endpoint resolution.
    return os.environ.get("AWS_ENDPOINT_URL", "").strip()


def ddb_table_name() -> str:
    return os.environ.get("DDB_TABLE_NAME", "replate")


def azure_storage_connection_string() -> str:
    return os.environ["AzureWebJobsStorage"]


def blob_container_uploads() -> str:
    return os.environ.get("BLOB_CONTAINER_UPLOADS", "uploads")


def queue_name_jobs() -> str:
    return os.environ.get("QUEUE_NAME_JOBS", "jobs")


def sas_token_expiry_minutes() -> int:
    return int(os.environ.get("SAS_TOKEN_EXPIRY_MINUTES", "15"))


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


def google_places_api_key() -> str:
    return os.environ["GOOGLE_PLACES_API_KEY"]


def places_timeout_seconds() -> float:
    return float(os.environ.get("PLACES_TIMEOUT_SECONDS", "8"))


def anthropic_api_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


def menu_fetch_model() -> str:
    return os.environ.get("MENU_FETCH_MODEL", "claude-sonnet-5")


def menu_fetch_timeout_seconds() -> float:
    return float(os.environ.get("MENU_FETCH_TIMEOUT_SECONDS", "60"))


def menu_fetch_max_retries() -> int:
    return int(os.environ.get("MENU_FETCH_MAX_RETRIES", "2"))


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


def content_safety_endpoint() -> str:
    # Optional, unlike the other service endpoints: blank means "no moderation
    # configured", which shared/content_safety.py reports as unchecked rather than
    # raising. Keeps local dev running without a Content Safety account.
    return os.environ.get("CONTENT_SAFETY_ENDPOINT", "")


def content_safety_key() -> str:
    return os.environ.get("CONTENT_SAFETY_KEY", "")


def content_safety_reject_severity() -> int:
    return int(os.environ.get("CONTENT_SAFETY_REJECT_SEVERITY", "4"))


def content_safety_timeout_seconds() -> float:
    return float(os.environ.get("CONTENT_SAFETY_TIMEOUT_SECONDS", "10"))


def content_safety_max_retries() -> int:
    return int(os.environ.get("CONTENT_SAFETY_MAX_RETRIES", "2"))
