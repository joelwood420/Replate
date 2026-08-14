from shared import config, http


def get_user_oid(event: dict) -> str:
    """Resolve the authenticated user's subject id for this request.

    COGNITO_ENABLED=false (default, local dev): reads a debug header
    (STUB_AUTH_HEADER_NAME) or falls back to STUB_DEFAULT_USER_OID - no real
    token validation, since no Cognito user pool exists yet.

    COGNITO_ENABLED=true (Phase 3): API Gateway's Cognito JWT authorizer validates
    the token *before* this Lambda is ever invoked - an unauthenticated request is
    rejected with a 401 at the gateway and never reaches here. So this is a read of
    the already-verified `sub` claim out of
    `event.requestContext.authorizer.jwt.claims`, not a validation step. Callers do
    not change.

    The identifier is still called `oid` throughout - Entra's name for it. Cognito
    calls it `sub`. Renaming it would touch every caller and every stored job item
    for no behavioural gain.
    """
    if not config.cognito_enabled():
        header_name = config.stub_auth_header_name()
        return http.get_header(event, header_name) or config.stub_default_user_oid()

    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    sub = claims.get("sub")
    if not sub:
        # The authorizer guarantees a verified token by the time we run, so an
        # absent `sub` is a misconfiguration (authorizer not attached to the route,
        # or an unexpected token shape) - not an untrusted caller. Fail loudly.
        raise PermissionError(
            "COGNITO_ENABLED=true but no verified `sub` claim on the request - the "
            "API Gateway JWT authorizer is missing or misconfigured for this route."
        )
    return sub
