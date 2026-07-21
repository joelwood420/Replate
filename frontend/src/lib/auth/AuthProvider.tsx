import { createContext, useCallback, useMemo, useState, type ReactNode } from 'react';
import { PublicClientApplication } from '@azure/msal-browser';
import { MsalProvider, useIsAuthenticated, useMsal } from '@azure/msal-react';
import { msalConfig } from './msalConfig';
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

const ENTRAID_ENABLED = import.meta.env.VITE_ENTRAID_ENABLED === 'true';
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

// Local dev / Phase 2: no real Entra tenant exists yet. Mirrors the backend's
// ENTRAID_ENABLED=false stub-auth seam (shared/auth.py) so a locally-created mock oid
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

// Phase 3 seam: real MSAL flow, structurally wired but inert until a real Entra tenant
// exists (no tenant to authenticate against yet, same spirit as the backend's
// NotImplementedError seam for ENTRAID_ENABLED=true).
function MsalAuthBridge({ children }: { children: ReactNode }) {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  const signIn = useCallback(() => {
    void instance.loginRedirect();
  }, [instance]);

  const signOut = useCallback(() => {
    void instance.logoutRedirect();
  }, [instance]);

  const account = accounts[0];
  const user: AuthUser | null = account
    ? {
        name: account.name ?? account.username,
        initials: initialsFromName(account.name ?? account.username),
        oid: (account.idTokenClaims?.oid as string | undefined) ?? account.homeAccountId,
      }
    : null;

  // No real token exchange yet - not exercised until Phase 3 provisions a tenant.
  const authHeaders = useMemo<AuthHeaders>(() => ({}), []);

  const value: AuthContextValue = { isAuthenticated, user, signIn, signOut, authHeaders };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

const msalInstance = ENTRAID_ENABLED ? new PublicClientApplication(msalConfig) : null;

export function AuthProvider({ children }: { children: ReactNode }) {
  if (msalInstance) {
    return (
      <MsalProvider instance={msalInstance}>
        <MsalAuthBridge>{children}</MsalAuthBridge>
      </MsalProvider>
    );
  }

  return <MockAuthProvider>{children}</MockAuthProvider>;
}
