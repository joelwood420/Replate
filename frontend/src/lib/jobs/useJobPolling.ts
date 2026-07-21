import { useEffect, useRef, useState } from 'react';
import { getJob, type JobDetail } from '../apiClient';
import { useAuth } from '../auth/useAuth';

const POLL_INTERVAL_MS = 3000;

export interface JobPollingState {
  job: JobDetail | null;
  error: string | null;
  isLoading: boolean;
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
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;

    async function poll() {
      try {
        const result = await getJob(jobId as string, authHeaders);
        if (cancelled) return;
        setJob(result);
        setIsLoading(false);
        if (result.status === 'Queued' || result.status === 'Processing') {
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
  }, [jobId, authHeaders]);

  return { job, error, isLoading };
}
