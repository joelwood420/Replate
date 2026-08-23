import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { listJobs, type JobSummary } from '../apiClient';
import { useAuth } from '../auth/useAuth';

// One read covers every tab. The backend already reads the user's whole job
// partition on each request and applies `saved`/`limit` in memory (see
// backend/shared/repository.list_jobs), so fetching a generous cap once and
// deriving the Home and Cookbook views client-side costs the same as a single
// old fetch - and lets tab switches render straight from cache with no spinner.
//
// The cap must be large enough to hold the user's ENTIRE list, because the
// Cookbook's saved filter now runs client-side over this one read. A smaller cap
// (say 100) would drop a saved dish that falls outside the newest-N total jobs,
// even when the user has few saved items - so this is effectively "all jobs".
// If a user ever exceeds it, the fix is real server-side paging, not a bigger cap.
const FULL_LIST_LIMIT = 1000;

export interface JobListState {
  jobs: JobSummary[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

interface JobsStore extends JobListState {
  /** Optimistically update one cached job in place (e.g. a save toggle). */
  patchJob: (jobId: string, changes: Partial<JobSummary>) => void;
}

const JobsContext = createContext<JobsStore | null>(null);

/**
 * The single source of truth for the user's job list, shared by every tab.
 *
 * Stale-while-revalidate: the cached list renders immediately on every visit and
 * a refresh runs in the background, so `isLoading` is true only on the first load
 * (when there is nothing to show) and a background failure never discards good
 * cached data. Mounted above the router, so the cache survives tab navigation.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const { authHeaders, isAuthenticated } = useAuth();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  // Start in the loading state when we'll fetch on mount, so an authenticated
  // first render shows the spinner rather than a one-frame empty flash.
  const [isLoading, setIsLoading] = useState(isAuthenticated);
  const [error, setError] = useState<string | null>(null);
  const hasData = useRef(false);
  const inFlight = useRef(false);

  const refetch = useCallback(() => {
    if (!isAuthenticated) return;
    if (inFlight.current) return; // dedupe overlapping refreshes (mount + focus, etc.)
    inFlight.current = true;
    if (!hasData.current) {
      // Spinner only when nothing is cached yet. Clear any prior error so a retry
      // shows the spinner alone, not the spinner and the stale error banner together.
      setIsLoading(true);
      setError(null);
    }
    listJobs({ limit: FULL_LIST_LIMIT }, authHeaders)
      .then((result) => {
        setJobs(result);
        hasData.current = true;
        setError(null);
      })
      .catch((err: unknown) => {
        // Keep showing stale data on a background failure; only surface an error
        // when there is nothing cached to fall back on.
        if (!hasData.current) {
          setError(err instanceof Error ? err.message : 'Failed to load dishes');
        }
      })
      .finally(() => {
        inFlight.current = false;
        setIsLoading(false);
      });
  }, [authHeaders, isAuthenticated]);

  // Prefetch as soon as the user is authenticated (before they reach any tab), and
  // drop the cache on sign-out so the next user never briefly sees these dishes.
  useEffect(() => {
    if (isAuthenticated) {
      refetch();
    } else {
      setJobs([]);
      hasData.current = false;
      setError(null);
      setIsLoading(false);
    }
  }, [isAuthenticated, refetch]);

  // Refresh when the tab regains focus, so returning to the app shows fresh dishes.
  useEffect(() => {
    window.addEventListener('focus', refetch);
    return () => window.removeEventListener('focus', refetch);
  }, [refetch]);

  const patchJob = useCallback((jobId: string, changes: Partial<JobSummary>) => {
    setJobs((prev) => prev.map((job) => (job.job_id === jobId ? { ...job, ...changes } : job)));
  }, []);

  const value = useMemo<JobsStore>(
    () => ({ jobs, isLoading, error, refetch, patchJob }),
    [jobs, isLoading, error, refetch, patchJob],
  );
  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>;
}

export function useJobsStore(): JobsStore {
  const ctx = useContext(JobsContext);
  if (!ctx) {
    throw new Error('useJobsStore must be used within a JobsProvider');
  }
  return ctx;
}
