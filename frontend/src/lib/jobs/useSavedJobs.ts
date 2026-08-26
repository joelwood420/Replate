import { useEffect } from 'react';
import { useJobsStore } from './JobsProvider';

// A live scan is auto-saved server-side only once identification finishes (is_saved flips
// true then), but the Cookbook is now where a scan lands to process in place, so it must
// also show a job that is still in flight or has just failed - neither of which is is_saved
// yet. Including these statuses shows the just-scanned dish immediately (as a processing
// card) and keeps a Failed scan visible with its retry state.
const IN_FLIGHT_OR_FAILED = new Set(['Queued', 'Processing', 'Failed']);

/**
 * The Cookbook view, derived from the shared cache. Exposes `patchJob` so the save toggle can
 * update the cache optimistically. Triggers a background refresh on mount.
 *
 * Shows a job when it is saved OR still in flight OR failed. A Cancelled scan (the user
 * deliberately stopped it) is dropped, and an un-hearted settled dish (is_saved false, not in
 * flight, not failed) falls out on its own.
 */
export function useSavedJobs() {
  const { jobs, isLoading, error, refetch, patchJob, removeJob } = useJobsStore();
  useEffect(() => {
    refetch();
  }, [refetch]);
  const cookbook = jobs.filter(
    (job) => job.status !== 'Cancelled' && (job.is_saved || IN_FLIGHT_OR_FAILED.has(job.status)),
  );
  return { jobs: cookbook, isLoading, error, refetch, patchJob, removeJob };
}
