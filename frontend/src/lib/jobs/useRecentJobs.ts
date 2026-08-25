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
  // "Recently Identified" only lists dishes that reached, or are on their way to, an
  // identification. A Failed stage-1 scan (bad photo, moderation reject, pipeline error)
  // and a Cancelled scan (the user stopped it) never produced one, so neither belongs here.
  // In-flight jobs (Queued/Processing) stay - they show their "still processing" state.
  const identified = jobs.filter((job) => job.status !== 'Failed' && job.status !== 'Cancelled');
  return { jobs: identified.slice(0, limit), isLoading, error, refetch };
}
