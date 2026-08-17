import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
  type CognitoUserSession,
} from 'amazon-cognito-identity-js';
import type { AuthUser } from './AuthProvider';

// The custom in-app Cognito integration. Replaces the hosted-UI redirect
// (react-oidc-context) with the browser SDK, so sign-up and sign-in happen inside
// Replate's own screens. The user pool client allows ALLOW_USER_SRP_AUTH and is a
// public client (GenerateSecret: false), which is exactly what this SDK needs.

const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID || '';
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || '';

// Small first-name-based initials, shared with the mock provider so both auth paths
// produce the same avatar text.
export function initialsFromName(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0]!.toUpperCase())
    .slice(0, 2)
    .join('');
}

let pool: CognitoUserPool | null = null;
function userPool(): CognitoUserPool {
  if (!pool) {
    if (!USER_POOL_ID || !CLIENT_ID) {
      throw new Error(
        'Cognito is enabled but VITE_COGNITO_USER_POOL_ID / VITE_COGNITO_CLIENT_ID are not set.',
      );
    }
    pool = new CognitoUserPool({ UserPoolId: USER_POOL_ID, ClientId: CLIENT_ID });
  }
  return pool;
}

function cognitoUser(email: string): CognitoUser {
  return new CognitoUser({ Username: email, Pool: userPool() });
}

// Map Cognito's error codes onto copy a user can act on. Falls back to the raw
// message rather than swallowing an unexpected failure.
function friendlyError(err: unknown): Error {
  const code = (err as { code?: string; name?: string })?.code ?? (err as { name?: string })?.name;
  const message = (err as { message?: string })?.message ?? 'Something went wrong. Please try again.';
  switch (code) {
    case 'UserNotConfirmedException':
      return new Error('Please verify your email before signing in.');
    case 'NotAuthorizedException':
      return new Error('Incorrect email or password.');
    case 'UserNotFoundException':
      return new Error('No account found with that email.');
    case 'UsernameExistsException':
      return new Error('An account with that email already exists.');
    case 'CodeMismatchException':
      return new Error("That code isn't right — check it and try again.");
    case 'ExpiredCodeException':
      return new Error('That code has expired. Request a new one.');
    case 'InvalidPasswordException':
      return new Error('Password must be at least 8 characters with upper, lower, and a number.');
    default:
      return new Error(message);
  }
}

// Turn a validated session into the shape the rest of the app already consumes.
// Display attributes come from the ID token; the bearer header uses the access
// token, whose client_id the API Gateway JWT authorizer validates as the audience.
function sessionToAuth(session: CognitoUserSession): { user: AuthUser; accessToken: string } {
  const claims = session.getIdToken().payload as { name?: string; email?: string; sub?: string };
  const name = claims.name ?? claims.email ?? '';
  return {
    user: { name, initials: initialsFromName(name), oid: claims.sub ?? '' },
    accessToken: session.getAccessToken().getJwtToken(),
  };
}

export function signUp(details: { name: string; email: string; password: string }): Promise<void> {
  const attributes = [new CognitoUserAttribute({ Name: 'name', Value: details.name })];
  return new Promise((resolve, reject) => {
    userPool().signUp(details.email, details.password, attributes, [], (err) => {
      if (err) return reject(friendlyError(err));
      resolve();
    });
  });
}

export function confirmSignUp(email: string, code: string): Promise<void> {
  return new Promise((resolve, reject) => {
    cognitoUser(email).confirmRegistration(code, true, (err) => {
      if (err) return reject(friendlyError(err));
      resolve();
    });
  });
}

export function resendCode(email: string): Promise<void> {
  return new Promise((resolve, reject) => {
    cognitoUser(email).resendConfirmationCode((err) => {
      if (err) return reject(friendlyError(err));
      resolve();
    });
  });
}

export function signIn(
  email: string,
  password: string,
): Promise<{ user: AuthUser; accessToken: string }> {
  const authDetails = new AuthenticationDetails({ Username: email, Password: password });
  return new Promise((resolve, reject) => {
    cognitoUser(email).authenticateUser(authDetails, {
      onSuccess: (session) => resolve(sessionToAuth(session)),
      onFailure: (err) => reject(friendlyError(err)),
    });
  });
}

// Restore a persisted session on load (the SDK keeps tokens in localStorage), so a
// refresh stays signed in. Resolves null when there is no valid session.
export function currentUser(): Promise<{ user: AuthUser; accessToken: string } | null> {
  return new Promise((resolve) => {
    const current = userPool().getCurrentUser();
    if (!current) return resolve(null);
    current.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session || !session.isValid()) return resolve(null);
      resolve(sessionToAuth(session));
    });
  });
}

export function signOut(): void {
  userPool().getCurrentUser()?.signOut();
}
