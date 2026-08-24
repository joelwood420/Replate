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
  // "Recently Identified" only lists dishes that were actually identified. A Failed
  // stage-1 scan (bad photo, moderation reject, or a pipeline error like a menu-fetch
  // timeout) never produced an identification, so it does not belong here.
  const identified = jobs.filter((job) => job.status !== 'Failed');
  return { jobs: identified.slice(0, limit), isLoading, error, refetch };
}
