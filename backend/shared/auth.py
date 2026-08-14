from shared import config, http


def get_user_oid(event: dict) -> str:
    """Resolve the authenticated user's subject id for this request.

    COGNITO_ENABLED=false (default, local dev): reads a debug header
    (STUB_AUTH_HEADER_NAME) or falls back to STUB_DEFAULT_USER_OID - no real
    token validation, since no Cognito user pool exists yet.

    COGNITO_ENABLED=true (Phase 3): not implemented yet. Once API Gateway fronts
    these handlers, its Cognito JWT authorizer validates the token before the
    Lambda runs, so this becomes a read of the `sub` claim out of
    `event.requestContext.authorizer.jwt.claims` rather than a validation step.
    Callers do not need to change.

    The identifier is still called `oid` throughout - Entra's name for it. Cognito
    calls it `sub`. Renaming it would touch every caller and every stored job item
    for no behavioural gain.
    """
    if not config.cognito_enabled():
        header_name = config.stub_auth_header_name()
        return http.get_header(event, header_name) or config.stub_default_user_oid()

    raise NotImplementedError(
        "COGNITO_ENABLED=true but real JWT handling is not implemented yet "
        "- that's Phase 3 scope. Set COGNITO_ENABLED=false for local dev."
    )
