import { useEffect } from 'react';
import { useJobsStore } from './JobsProvider';

/**
 * The Home "recently identified" view: newest N jobs, derived from the shared
 * cache. The backend already returns the partition newest-first, so this is a
 * slice. Triggers a background refresh on mount (cache renders instantly).
 */
export function useRecentJobs(limit = 10) {
  const { jobs, isLoading, error, refetch } = useJobsStore();
  useEffect(() => {
    refetch();
  }, [refetch]);
  return { jobs: jobs.slice(0, limit), isLoading, error, refetch };
}
