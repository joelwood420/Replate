import type { UserManagerSettings } from 'oidc-client-ts';

/**
 * Amazon Cognito is a standard OIDC provider, so this is plain OIDC config
 * rather than anything Cognito-specific - which is the point. The MSAL setup it
 * replaced needed a vendor SDK; this needs an authority URL.
 *
 * `authority` is the user pool issuer:
 *   https://cognito-idp.<region>.amazonaws.com/<userPoolId>
 *
 * None of these exist until Phase 3 provisions the pool, so every value is
 * env-driven and the provider stays mocked while they are blank.
 */
export const cognitoConfig: UserManagerSettings = {
  authority: import.meta.env.VITE_COGNITO_AUTHORITY || '',
  client_id: import.meta.env.VITE_COGNITO_CLIENT_ID || '',
  redirect_uri: import.meta.env.VITE_COGNITO_REDIRECT_URI || window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  // `code` is Authorization Code + PKCE. Cognito supports the implicit flow too;
  // it should not be used - it puts tokens in the URL fragment.
  response_type: 'code',
  scope: import.meta.env.VITE_COGNITO_SCOPE || 'openid profile email',
  // Tokens in memory rather than sessionStorage. Cognito access tokens are
  // short-lived and silently renewed, so persisting them buys little and widens
  // the XSS blast radius.
  automaticSilentRenew: true,
};
