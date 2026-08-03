import { useCallback, useEffect, useRef, useState } from 'react';
import { getJob, type JobDetail, type JobStatusValue } from '../apiClient';
import { useAuth } from '../auth/useAuth';

const POLL_INTERVAL_MS = 3000;

/**
 * Statuses where more work is in flight, so the job is worth polling again.
 * `Identified` is deliberately absent - stage 1 is finished and stage 2 won't start
 * until the user asks for it, so an un-reverse-engineered dish must not poll forever.
 */
const IN_FLIGHT_STATUSES: JobStatusValue[] = ['Queued', 'Processing', 'Generating'];

export interface JobPollingState {
  job: JobDetail | null;
  error: string | null;
  isLoading: boolean;
  /**
   * Re-reads the job and resumes polling. Needed after an action that puts the job
   * back in flight - pressing "Reverse engineer" moves it from the terminal
   * `Identified` state to `Generating`, which polling has already stopped for.
   */
  refetch: () => void;
}

/**
 * Polls GET /api/jobs/{jobId} until the job reaches a terminal state. This is the
 * "real-time listener" seam - Phase 3 can swap the polling body for a SignalR/Web
 * PubSub subscription without changing what consumers of this hook see.
 */
export function useJobPolling(jobId: string | undefined): JobPollingState {
  const { authHeaders } = useAuth();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const refetch = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;

    async function poll() {
      try {
        const result = await getJob(jobId as string, authHeaders);
        if (cancelled) return;
        setJob(result);
        setError(null);
        setIsLoading(false);
        if (IN_FLIGHT_STATUSES.includes(result.status)) {
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load job status');
        setIsLoading(false);
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId, authHeaders, reloadToken]);

  return { job, error, isLoading, refetch };
}
