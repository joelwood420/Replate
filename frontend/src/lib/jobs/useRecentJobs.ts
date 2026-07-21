import { useJobList } from './useJobList';

export function useRecentJobs(limit = 10) {
  return useJobList({ limit });
}
