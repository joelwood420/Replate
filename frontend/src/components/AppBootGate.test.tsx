import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { AppBootGate } from './AppBootGate';

vi.mock('../lib/auth/useAuth', () => ({ useAuth: vi.fn() }));
vi.mock('../lib/jobs/JobsProvider', () => ({ useJobsStore: vi.fn() }));
vi.mock('../screens/SplashScreen', () => ({ SplashScreen: () => <div>SPLASH</div> }));

import { useAuth } from '../lib/auth/useAuth';
import { useJobsStore } from '../lib/jobs/JobsProvider';

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseJobsStore = vi.mocked(useJobsStore);

function setAuth(isReady: boolean, isAuthenticated: boolean) {
  mockedUseAuth.mockReturnValue({ isReady, isAuthenticated } as unknown as ReturnType<typeof useAuth>);
}
function setJobs(hasLoadedOnce: boolean) {
  mockedUseJobsStore.mockReturnValue({ hasLoadedOnce } as unknown as ReturnType<typeof useJobsStore>);
}

function renderGate() {
  return render(
    <AppBootGate>
      <div>APP</div>
    </AppBootGate>,
  );
}

describe('AppBootGate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('shows the splash until the minimum time elapses, even when everything is ready', async () => {
    setAuth(true, false);
    setJobs(true);
    renderGate();

    expect(screen.getByText('SPLASH')).toBeInTheDocument();
    expect(screen.queryByText('APP')).not.toBeInTheDocument();

    // Boot completes: the app mounts behind the splash, which lingers as an exiting
    // overlay playing its dissolve. Async advance so the reveal timer, scheduled in a
    // passive effect, is registered before we advance through it.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2400);
    });

    expect(screen.getByText('APP')).toBeInTheDocument();
    expect(screen.getByText('SPLASH')).toBeInTheDocument();

    // The dissolve finishes and the splash unmounts, leaving the app.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(720);
    });

    expect(screen.getByText('APP')).toBeInTheDocument();
    expect(screen.queryByText('SPLASH')).not.toBeInTheDocument();
  });

  it('holds the splash past the minimum while auth is still restoring', () => {
    setAuth(false, false); // session not restored yet
    setJobs(true);
    renderGate();

    act(() => vi.advanceTimersByTime(2400));

    expect(screen.getByText('SPLASH')).toBeInTheDocument();
    expect(screen.queryByText('APP')).not.toBeInTheDocument();
  });

  it('holds the splash for a signed-in user until the first job fetch settles', async () => {
    setAuth(true, true);
    setJobs(false); // prefetch in flight
    const { rerender } = renderGate();

    act(() => vi.advanceTimersByTime(2400));
    expect(screen.getByText('SPLASH')).toBeInTheDocument();

    // Prefetch settles: the app mounts and the splash begins its dissolve.
    setJobs(true);
    rerender(
      <AppBootGate>
        <div>APP</div>
      </AppBootGate>,
    );

    expect(screen.getByText('APP')).toBeInTheDocument();

    // The dissolve finishes and the splash unmounts.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(720);
    });
    expect(screen.queryByText('SPLASH')).not.toBeInTheDocument();
  });

  it('does not wait on the job list for a signed-out user', async () => {
    setAuth(true, false);
    setJobs(false); // never fetched, and never will while signed out
    renderGate();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2400);
    });

    expect(screen.getByText('APP')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(720);
    });
    expect(screen.queryByText('SPLASH')).not.toBeInTheDocument();
  });
});
