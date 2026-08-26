import { useEffect } from 'react';
import { useJobsStore } from './JobsProvider';

/**
 * The Cookbook view: saved jobs, derived from the shared cache. Exposes `patchJob` so the
 * save toggle can update the cache optimistically. Triggers a background refresh on mount.
 *
 * A scan lands here to process in place (that's where capture now navigates), so in-flight,
 * identified, completed and Failed jobs all belong - a Failed scan shows a retry state on its
 * card. A Cancelled scan is one the user deliberately stopped, so it's dropped rather than
 * left sitting in the cookbook.
 */
export function useSavedJobs() {
  const { jobs, isLoading, error, refetch, patchJob } = useJobsStore();
  useEffect(() => {
    refetch();
  }, [refetch]);
  const saved = jobs.filter((job) => job.is_saved && job.status !== 'Cancelled');
  return { jobs: saved, isLoading, error, refetch, patchJob };
}
