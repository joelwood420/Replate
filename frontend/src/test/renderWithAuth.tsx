import { useMemo, type ReactNode } from 'react';
import { AuthContext, type AuthContextValue } from '../lib/auth/AuthProvider';

/**
 * A fully-populated auth context value for tests, with no-op actions by default.
 * Create it ONCE per test (not inline in a render) so `authHeaders` keeps a stable
 * identity: hooks like useJobPolling/useJobList re-run their effect when it changes,
 * and an unstable value would re-fetch on every render.
 */
export function makeAuthValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    isAuthenticated: true,
    user: { name: 'Test Cook', initials: 'TC', oid: 'oid-test' },
    signIn: async () => {},
    signUp: async () => ({ needsConfirmation: false }),
    confirmSignUp: async () => {},
    resendConfirmationCode: async () => {},
    signOut: () => {},
    updateDisplayName: () => {},
    authHeaders: { 'X-Debug-User-Oid': 'oid-test' },
    ...overrides,
  };
}

/** Wraps children in an AuthContext provider so hooks/components that call useAuth() work. */
export function AuthWrapper({ value, children }: { value?: AuthContextValue; children: ReactNode }) {
  const fallback = useMemo(() => makeAuthValue(), []);
  return <AuthContext.Provider value={value ?? fallback}>{children}</AuthContext.Provider>;
}
