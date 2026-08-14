import { createContext, useCallback, useMemo, useState, type ReactNode } from 'react';
import { AuthProvider as OidcProvider, useAuth as useOidc } from 'react-oidc-context';
import { cognitoConfig } from './cognitoConfig';
import type { AuthHeaders } from '../apiClient';

export interface AuthUser {
  name: string;
  initials: string;
  oid: string;
}

export interface AuthContextValue {
  isAuthenticated: boolean;
  user: AuthUser | null;
  signIn: () => void;
  signOut: () => void;
  authHeaders: AuthHeaders;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

const COGNITO_ENABLED = import.meta.env.VITE_COGNITO_ENABLED === 'true';
const STUB_AUTH_HEADER_NAME = import.meta.env.VITE_STUB_AUTH_HEADER_NAME || 'X-Debug-User-Oid';
const STUB_DEFAULT_USER_OID =
  import.meta.env.VITE_STUB_DEFAULT_USER_OID || '00000000-0000-0000-0000-000000000001';
const MOCK_SESSION_KEY = 'replate.mockAuth';

function initialsFromName(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0]!.toUpperCase())
    .slice(0, 2)
    .join('');
}

// Local dev / Phase 0: no Cognito user pool exists yet. Mirrors the backend's
// COGNITO_ENABLED=false stub-auth seam (shared/auth.py) so a locally-created mock oid
// matches STUB_DEFAULT_USER_OID and the two sides just work together.
function MockAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = sessionStorage.getItem(MOCK_SESSION_KEY);
    return stored ? (JSON.parse(stored) as AuthUser) : null;
  });

  const signIn = useCallback(() => {
    const mockUser: AuthUser = {
      name: 'Elena Marchetti',
      initials: initialsFromName('Elena Marchetti'),
      oid: STUB_DEFAULT_USER_OID,
    };
    sessionStorage.setItem(MOCK_SESSION_KEY, JSON.stringify(mockUser));
    setUser(mockUser);
  }, []);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(MOCK_SESSION_KEY);
    setUser(null);
  }, []);

  const authHeaders = useMemo<AuthHeaders>(
    () => (user ? { [STUB_AUTH_HEADER_NAME]: user.oid } : {}),
    [user],
  );

  const value: AuthContextValue = { isAuthenticated: user !== null, user, signIn, signOut, authHeaders };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Phase 3 seam: the real Cognito flow, structurally wired but inert until a user
// pool exists. Unlike the MSAL bridge this replaced, it does produce a usable
// Authorization header - API Gateway's JWT authorizer expects a bearer token, so
// there is nothing left to fill in here once the pool is provisioned.
function CognitoAuthBridge({ children }: { children: ReactNode }) {
  const oidc = useOidc();

  const signIn = useCallback(() => {
    void oidc.signinRedirect();
  }, [oidc]);

  const signOut = useCallback(() => {
    void oidc.signoutRedirect();
  }, [oidc]);

  const profile = oidc.user?.profile;
  // Cognito puts the stable user identifier in `sub`. Entra called it `oid`; the
  // field name is kept so nothing downstream of this context has to change.
  const displayName = (profile?.name as string | undefined) ?? profile?.email ?? '';
  const user: AuthUser | null = profile
    ? {
        name: displayName,
        initials: initialsFromName(displayName),
        oid: profile.sub ?? '',
      }
    : null;

  const accessToken = oidc.user?.access_token;
  const authHeaders = useMemo<AuthHeaders>(() => {
    // Built up rather than returned as a ternary: a bare `{}` in one branch makes
    // TypeScript infer `Authorization?: undefined`, which the index signature on
    // AuthHeaders (string values only) then rejects.
    const headers: AuthHeaders = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return headers;
  }, [accessToken]);

  const value: AuthContextValue = {
    isAuthenticated: oidc.isAuthenticated,
    user,
    signIn,
    signOut,
    authHeaders,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  if (COGNITO_ENABLED) {
    return (
      <OidcProvider {...cognitoConfig}>
        <CognitoAuthBridge>{children}</CognitoAuthBridge>
      </OidcProvider>
    );
  }

  return <MockAuthProvider>{children}</MockAuthProvider>;
}
