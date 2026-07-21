import azure.functions as func

from shared import config


def get_user_oid(req: func.HttpRequest) -> str:
    """Resolve the authenticated user's Entra object id (oid) for this request.

    ENTRAID_ENABLED=false (default, local dev): reads a debug header
    (STUB_AUTH_HEADER_NAME) or falls back to STUB_DEFAULT_USER_OID - no real
    token validation, since no Entra tenant exists yet.

    ENTRAID_ENABLED=true (Phase 3): not implemented yet - real Entra ID JWT
    validation gets wired in here once a real tenant/app registration and the
    frontend exist. Callers (upload_http, job_result_http) will not need to
    change when that lands.
    """
    if not config.entraid_enabled():
        header_name = config.stub_auth_header_name()
        return req.headers.get(header_name) or config.stub_default_user_oid()

    raise NotImplementedError(
        "ENTRAID_ENABLED=true but real Entra ID JWT validation is not implemented yet "
        "- that's Phase 3 scope. Set ENTRAID_ENABLED=false for local dev."
    )
