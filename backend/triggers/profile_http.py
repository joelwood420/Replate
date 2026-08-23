from shared import http, repository
from shared.auth import get_user_oid

MAX_DISPLAY_NAME_LEN = 80


def _profile_body(profile: dict) -> dict:
    """The public shape of a profile: identity fields only, never the keys."""
    return {
        "display_name": profile.get("display_name"),
        "email": profile.get("email"),
        "created_at": profile.get("created_at"),
    }


def get_run(user_oid: str) -> dict:
    return {"status_code": 200, "body": _profile_body(repository.get_profile(user_oid))}


def update_run(user_oid: str, display_name) -> dict:
    if not isinstance(display_name, str):
        return {"status_code": 400, "body": {"error": "display_name is required"}}
    trimmed = display_name.strip()
    if not trimmed:
        return {"status_code": 400, "body": {"error": "display_name cannot be empty"}}
    if len(trimmed) > MAX_DISPLAY_NAME_LEN:
        return {
            "status_code": 400,
            "body": {"error": f"display_name cannot exceed {MAX_DISPLAY_NAME_LEN} characters"},
        }

    return {"status_code": 200, "body": _profile_body(repository.update_profile(user_oid, trimmed))}


def get_handler(event, context=None):
    """GET /api/profile"""
    return http.from_outcome(get_run(get_user_oid(event)))


def update_handler(event, context=None):
    """PUT /api/profile"""
    display_name = http.get_body(event).get("display_name")
    return http.from_outcome(update_run(get_user_oid(event), display_name))
