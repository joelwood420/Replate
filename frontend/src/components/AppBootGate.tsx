import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '../lib/auth/useAuth';
import { useJobsStore } from '../lib/jobs/JobsProvider';
import { SplashScreen } from '../screens/SplashScreen';

// The splash stays up for at least this long so the branding always registers,
// even on a warm/instant load. Kept in step with the logo animation duration.
const MIN_SPLASH_MS = 2400;

// After boot completes, the splash lingers this long as an exiting overlay, playing
// its dissolve while the app fades up behind it. A touch longer than the CSS exit
// (680ms) so the layer is fully clear before it unmounts, avoiding any pop.
const REVEAL_MS = 720;

type Phase = 'boot' | 'revealing' | 'done';

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
  const [phase, setPhase] = useState<Phase>('boot');

  useEffect(() => {
    const timer = setTimeout(() => setMinElapsed(true), MIN_SPLASH_MS);
    return () => clearTimeout(timer);
  }, []);

  // A signed-out user has nothing to prefetch, so only wait on the job list when
  // authenticated. Each condition is monotonic (false -> true once), so the gate
  // never flips back to the splash after revealing the app.
  const dataReady = !isAuthenticated || hasLoadedOnce;
  const booting = !minElapsed || !isReady || !dataReady;

  // Once boot finishes, hold the splash one more beat as an exiting overlay so the
  // candlelight hands off to the app instead of hard-cutting. Monotonic:
  // boot -> revealing -> done, never back.
  useEffect(() => {
    if (phase === 'boot' && !booting) setPhase('revealing');
  }, [booting, phase]);

  // The dissolve timer lives in its own effect so entering `revealing` doesn't
  // immediately re-run (and clear) the timer that ends it. Cleanup only fires when
  // phase leaves `revealing` for `done`, by which point the timer has already run.
  useEffect(() => {
    if (phase !== 'revealing') return;
    const timer = setTimeout(() => setPhase('done'), REVEAL_MS);
    return () => clearTimeout(timer);
  }, [phase]);

  if (phase === 'boot') return <SplashScreen />;
  if (phase === 'done') return <>{children}</>;

  // Revealing: the app is mounted and ready underneath (kept in the same tree slot
  // across revealing -> done, so it never remounts), while the splash overlays it,
  // plays its dissolve, and fades away to unveil it.
  return (
    <>
      {children}
      <SplashScreen exiting />
    </>
  );
}
