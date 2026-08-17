import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as cognito from './cognitoClient';
import { initialsFromName } from './cognitoClient';
import type { AuthHeaders } from '../apiClient';

export interface AuthUser {
  name: string;
  initials: string;
  oid: string;
}

export interface SignUpDetails {
  name: string;
  email: string;
  password: string;
}

export interface AuthContextValue {
  isAuthenticated: boolean;
  user: AuthUser | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (details: SignUpDetails) => Promise<{ needsConfirmation: boolean }>;
  confirmSignUp: (email: string, code: string) => Promise<void>;
  resendConfirmationCode: (email: string) => Promise<void>;
  signOut: () => void;
  authHeaders: AuthHeaders;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

const COGNITO_ENABLED = import.meta.env.VITE_COGNITO_ENABLED === 'true';
const STUB_AUTH_HEADER_NAME = import.meta.env.VITE_STUB_AUTH_HEADER_NAME || 'X-Debug-User-Oid';
const STUB_DEFAULT_USER_OID =
  import.meta.env.VITE_STUB_DEFAULT_USER_OID || '00000000-0000-0000-0000-000000000001';
const MOCK_SESSION_KEY = 'replate.mockAuth';
const MOCK_ACCOUNTS_KEY = 'replate.mockAccounts';

// ---- Mock provider ------------------------------------------------------------------
// Local dev / Phase 0: no Cognito user pool is contacted. Mirrors the real provider's
// full sign-up -> verify -> sign-in shape (shared/auth.py's COGNITO_ENABLED=false stub
// seam) so the custom auth screens can be built and demoed without real accounts or
// email codes. Any 6-digit verification code is accepted.

type MockAccounts = Record<string, { name: string; password: string }>;

function readMockAccounts(): MockAccounts {
  const stored = sessionStorage.getItem(MOCK_ACCOUNTS_KEY);
  return stored ? (JSON.parse(stored) as MockAccounts) : {};
}

function nameFromEmail(email: string): string {
  const local = email.split('@')[0] ?? 'Cook';
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part[0]!.toUpperCase() + part.slice(1))
    .join(' ');
}

function MockAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = sessionStorage.getItem(MOCK_SESSION_KEY);
    return stored ? (JSON.parse(stored) as AuthUser) : null;
  });

  const startSession = useCallback((name: string) => {
    const mockUser: AuthUser = { name, initials: initialsFromName(name), oid: STUB_DEFAULT_USER_OID };
    sessionStorage.setItem(MOCK_SESSION_KEY, JSON.stringify(mockUser));
    setUser(mockUser);
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const accounts = readMockAccounts();
      const account = accounts[email.toLowerCase()];
      if (account) {
        if (account.password !== password) throw new Error('Incorrect email or password.');
        startSession(account.name);
      } else {
        // No account created this session — accept it so the plain "Log in" demo works.
        startSession(nameFromEmail(email));
      }
    },
    [startSession],
  );

  const signUp = useCallback(async (details: SignUpDetails) => {
    const accounts = readMockAccounts();
    accounts[details.email.toLowerCase()] = { name: details.name, password: details.password };
    sessionStorage.setItem(MOCK_ACCOUNTS_KEY, JSON.stringify(accounts));
    return { needsConfirmation: true };
  }, []);

  const confirmSignUp = useCallback(async (_email: string, code: string) => {
    if (!/^\d{6}$/.test(code)) throw new Error("That code isn't right — enter the 6-digit code.");
  }, []);

  const resendConfirmationCode = useCallback(async (_email: string) => {
    /* mock: nothing to resend */
  }, []);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(MOCK_SESSION_KEY);
    setUser(null);
  }, []);

  const authHeaders = useMemo<AuthHeaders>(
    () => (user ? { [STUB_AUTH_HEADER_NAME]: user.oid } : {}),
    [user],
  );

  const value: AuthContextValue = {
    isAuthenticated: user !== null,
    user,
    signIn,
    signUp,
    confirmSignUp,
    resendConfirmationCode,
    signOut,
    authHeaders,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---- Custom Cognito provider --------------------------------------------------------
// The real user pool via the in-app SDK (cognitoClient), replacing the hosted-UI
// redirect. Sign-up/sign-in happen in Replate's own screens; the SDK persists tokens
// to localStorage, so a refresh restores the session.

function CustomCognitoProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<{ user: AuthUser; accessToken: string } | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    cognito.currentUser().then((restored) => {
      setSession(restored);
      setReady(true);
    });
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    setSession(await cognito.signIn(email, password));
  }, []);

  const signUp = useCallback(async (details: SignUpDetails) => {
    await cognito.signUp(details);
    return { needsConfirmation: true };
  }, []);

  const confirmSignUp = useCallback((email: string, code: string) => cognito.confirmSignUp(email, code), []);

  const resendConfirmationCode = useCallback((email: string) => cognito.resendCode(email), []);

  const signOut = useCallback(() => {
    cognito.signOut();
    setSession(null);
  }, []);

  const authHeaders = useMemo<AuthHeaders>(() => {
    // Built up rather than a ternary: a bare `{}` branch makes TypeScript infer
    // `Authorization?: undefined`, which AuthHeaders' string-only index rejects.
    const headers: AuthHeaders = {};
    if (session) headers.Authorization = `Bearer ${session.accessToken}`;
    return headers;
  }, [session]);

  const value: AuthContextValue = {
    isAuthenticated: session !== null,
    user: session?.user ?? null,
    signIn,
    signUp,
    confirmSignUp,
    resendConfirmationCode,
    signOut,
    authHeaders,
  };

  // Hold the app until the persisted session is restored, so a hard refresh on a
  // protected route doesn't bounce to /signin before the session is known.
  if (!ready) return null;

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  if (COGNITO_ENABLED) {
    return <CustomCognitoProvider>{children}</CustomCognitoProvider>;
  }
  return <MockAuthProvider>{children}</MockAuthProvider>;
}
