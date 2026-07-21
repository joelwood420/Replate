import { useCallback, useEffect, useState } from 'react';
import { listJobs, type JobSummary } from '../apiClient';
import { useAuth } from '../auth/useAuth';

export interface JobListState {
  jobs: JobSummary[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Shared fetch/loading/error state behind useRecentJobs and useSavedJobs. */
export function useJobList(options: { saved?: boolean; limit?: number }): JobListState {
  const { authHeaders, isAuthenticated } = useAuth();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    listJobs(options, authHeaders)
      .then((result) => {
        setJobs(result);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load dishes');
      })
      .finally(() => setIsLoading(false));
  }, [authHeaders, isAuthenticated, options.saved, options.limit]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { jobs, isLoading, error, refetch };
}
