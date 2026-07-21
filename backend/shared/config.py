import os

from dotenv import load_dotenv

load_dotenv()


def sql_server() -> str:
    return os.environ["SQL_SERVER"]


def sql_database() -> str:
    return os.environ["SQL_DATABASE"]


def sql_uid() -> str:
    return os.environ["SQL_UID"]


def sql_pwd() -> str:
    return os.environ["SQL_PWD"]


def sql_odbc_driver() -> str:
    return os.environ.get("SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")


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


def entraid_enabled() -> bool:
    return os.environ.get("ENTRAID_ENABLED", "false").strip().lower() in ("1", "true", "yes")
