import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '../lib/auth/useAuth';
import { useJobsStore } from '../lib/jobs/JobsProvider';
import { SplashScreen } from '../screens/SplashScreen';

// The splash stays up for at least this long so the branding always registers,
// even on a warm/instant load. Kept in step with the logo animation duration.
const MIN_SPLASH_MS = 2400;

/**
 * Shows the splash on every fresh page load, whatever URL was opened, while the
 * app boots in the background (auth session restore, then the first job-list
 * fetch for a signed-in user). Only once boot is genuinely done AND the minimum
 * splash time has passed does it reveal the app, so the first screen is ready with
 * no spinner. Because it sits above the router, it fires once per page load, not on
 * in-app navigation.
 */
export function AppBootGate({ children }: { children: ReactNode }) {
  const { isReady, isAuthenticated } = useAuth();
  const { hasLoadedOnce } = useJobsStore();
  const [minElapsed, setMinElapsed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMinElapsed(true), MIN_SPLASH_MS);
    return () => clearTimeout(timer);
  }, []);

  // A signed-out user has nothing to prefetch, so only wait on the job list when
  // authenticated. Each condition is monotonic (false -> true once), so the gate
  // never flips back to the splash after revealing the app.
  const dataReady = !isAuthenticated || hasLoadedOnce;
  const booting = !minElapsed || !isReady || !dataReady;

  if (booting) return <SplashScreen />;
  return <>{children}</>;
}
