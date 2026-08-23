import { useEffect } from 'react';
import { useJobsStore } from './JobsProvider';

/**
 * The Cookbook view: saved jobs only, derived from the shared cache (same read
 * that feeds Home). Exposes `patchJob` so the save toggle can update the cache
 * optimistically. Triggers a background refresh on mount.
 */
export function useSavedJobs() {
  const { jobs, isLoading, error, refetch, patchJob } = useJobsStore();
  useEffect(() => {
    refetch();
  }, [refetch]);
  return { jobs: jobs.filter((job) => job.is_saved), isLoading, error, refetch, patchJob };
}
