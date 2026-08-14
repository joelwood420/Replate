import os

from dotenv import load_dotenv

# Load a .env only for local dev / tests. In Lambda, AWS_LAMBDA_FUNCTION_NAME is always
# set - and load_dotenv() fills in any *unset* var, so a .env accidentally packaged into
# the function zip would silently reintroduce local config (e.g. AWS_ENDPOINT_URL pointing
# at LocalStack) in production. Gating on the Lambda marker makes that impossible.
if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    load_dotenv()


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


def google_places_api_key() -> str:
    return os.environ["GOOGLE_PLACES_API_KEY"]


def places_timeout_seconds() -> float:
    return float(os.environ.get("PLACES_TIMEOUT_SECONDS", "8"))


# --- Amazon Bedrock -----------------------------------------------------------------
# No API key: the Lambda's execution role authenticates, so only model ids are
# configured. Model access must be granted per-model, per-region in the Bedrock
# console before the first call - CloudFormation cannot do it.


def bedrock_menu_model_id() -> str:
    return os.environ.get("BEDROCK_MENU_MODEL_ID", "")


def bedrock_vision_model_id() -> str:
    return os.environ.get("BEDROCK_VISION_MODEL_ID", "")


def bedrock_generator_model_id() -> str:
    return os.environ.get("BEDROCK_GENERATOR_MODEL_ID", "")


def bedrock_embedding_model_id() -> str:
    return os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "")


def menu_fetch_timeout_seconds() -> float:
    return float(os.environ.get("MENU_FETCH_TIMEOUT_SECONDS", "60"))


def menu_fetch_max_retries() -> int:
    return int(os.environ.get("MENU_FETCH_MAX_RETRIES", "2"))


# --- Menu page discovery ------------------------------------------------------------
# Bedrock does not expose Anthropic's server-side web_search tool, so finding a menu
# page needs a third-party SERP provider. This is the only stored API key the AWS
# design introduces; everything else authenticates by IAM.


def serp_api_key() -> str:
    return os.environ.get("SERP_API_KEY", "")


def serp_api_endpoint() -> str:
    return os.environ.get("SERP_API_ENDPOINT", "https://api.search.brave.com/res/v1/web/search")


def serp_timeout_seconds() -> float:
    return float(os.environ.get("SERP_TIMEOUT_SECONDS", "10"))


def serp_max_results() -> int:
    return int(os.environ.get("SERP_MAX_RESULTS", "3"))


def page_fetch_timeout_seconds() -> float:
    return float(os.environ.get("PAGE_FETCH_TIMEOUT_SECONDS", "15"))


def page_fetch_max_chars() -> int:
    # Cap what reaches the model. A restaurant page with a huge nav or embedded
    # script can otherwise blow the context window and the token bill for one job.
    return int(os.environ.get("PAGE_FETCH_MAX_CHARS", "40000"))


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
