import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { AuthWrapper, makeAuthValue } from '../../test/renderWithAuth';
import type { JobDetail, JobStatusValue } from '../apiClient';
import { useJobPolling } from './useJobPolling';

vi.mock('../apiClient', () => ({
  getJob: vi.fn(),
}));

import { getJob } from '../apiClient';

const mockedGetJob = vi.mocked(getJob);

function job(status: JobStatusValue): JobDetail {
  return {
    job_id: 'job-1',
    status,
    image_url: 'https://example.test/1.jpg',
    is_saved: false,
    created_at: null,
  };
}

/** Advance fake timers and flush the awaited getJob promise, inside act(). */
async function flush(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('useJobPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedGetJob.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls every 3s while in flight and stops once Identified', async () => {
    mockedGetJob.mockResolvedValueOnce(job('Processing')).mockResolvedValueOnce(job('Identified'));
    const authValue = makeAuthValue();

    const { result } = renderHook(() => useJobPolling('job-1'), {
      wrapper: ({ children }) => <AuthWrapper value={authValue}>{children}</AuthWrapper>,
    });

    await flush(0); // initial poll
    expect(result.current.job?.status).toBe('Processing');
    expect(result.current.isLoading).toBe(false);
    expect(mockedGetJob).toHaveBeenCalledTimes(1);

    await flush(3000); // second poll -> Identified (terminal for stage 1)
    expect(result.current.job?.status).toBe('Identified');
    expect(mockedGetJob).toHaveBeenCalledTimes(2);

    // Identified is not in-flight: no further polling however long we wait.
    await flush(9000);
    expect(mockedGetJob).toHaveBeenCalledTimes(2);
  });

  it('surfaces an error and stops polling on failure', async () => {
    mockedGetJob.mockRejectedValueOnce(new Error('boom'));
    const authValue = makeAuthValue();

    const { result } = renderHook(() => useJobPolling('job-1'), {
      wrapper: ({ children }) => <AuthWrapper value={authValue}>{children}</AuthWrapper>,
    });

    await flush(0);
    expect(result.current.error).toBe('boom');
    expect(result.current.isLoading).toBe(false);

    await flush(9000);
    expect(mockedGetJob).toHaveBeenCalledTimes(1);
  });

  it('refetch() resumes polling after the job is put back in flight', async () => {
    mockedGetJob
      .mockResolvedValueOnce(job('Identified')) // initial: terminal, no timer scheduled
      .mockResolvedValueOnce(job('Generating')) // after refetch
      .mockResolvedValueOnce(job('Completed')); // next poll
    const authValue = makeAuthValue();

    const { result } = renderHook(() => useJobPolling('job-1'), {
      wrapper: ({ children }) => <AuthWrapper value={authValue}>{children}</AuthWrapper>,
    });

    await flush(0);
    expect(result.current.job?.status).toBe('Identified');
    expect(mockedGetJob).toHaveBeenCalledTimes(1);

    // Idle at Identified.
    await flush(6000);
    expect(mockedGetJob).toHaveBeenCalledTimes(1);

    // Pressing "Reverse engineer" calls refetch(), which resumes polling.
    await act(async () => {
      result.current.refetch();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.status).toBe('Generating');
    expect(mockedGetJob).toHaveBeenCalledTimes(2);

    await flush(3000);
    expect(result.current.job?.status).toBe('Completed');
    expect(mockedGetJob).toHaveBeenCalledTimes(3);
  });
});
