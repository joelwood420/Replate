import { useJobList } from './useJobList';

export function useSavedJobs() {
  return useJobList({ saved: true });
}
