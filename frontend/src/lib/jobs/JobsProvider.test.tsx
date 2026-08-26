import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { AuthWrapper, makeAuthValue } from '../../test/renderWithAuth';
import type { AuthContextValue } from '../auth/AuthProvider';
import type { JobSummary } from '../apiClient';
import { JobsProvider, useJobsStore } from './JobsProvider';
import { useSavedJobs } from './useSavedJobs';

vi.mock('../apiClient', () => ({
  listJobs: vi.fn(),
}));

import { listJobs } from '../apiClient';

const mockedListJobs = vi.mocked(listJobs);

function makeJob(overrides: Partial<JobSummary> & Pick<JobSummary, 'job_id'>): JobSummary {
  return {
    status: 'Completed',
    is_saved: false,
    created_at: '2026-08-22T10:00:00.000Z',
    dish_name: 'Cacio e pepe',
    restaurant_name: 'Trattoria',
    image_url: 'https://example.test/1.jpg',
    ...overrides,
  };
}

const sampleJobs: JobSummary[] = [
  makeJob({ job_id: 'job-1', is_saved: true, created_at: '2026-08-22T12:00:00.000Z' }),
  makeJob({ job_id: 'job-2', is_saved: false, created_at: '2026-08-22T11:00:00.000Z' }),
  makeJob({ job_id: 'job-3', is_saved: true, created_at: '2026-08-22T10:00:00.000Z' }),
];

function wrapperFor(authValue: AuthContextValue) {
  return ({ children }: { children: ReactNode }) => (
    <AuthWrapper value={authValue}>
      <JobsProvider>{children}</JobsProvider>
    </AuthWrapper>
  );
}

describe('JobsProvider', () => {
  beforeEach(() => {
    mockedListJobs.mockReset();
  });

  it('loads the full list once with a whole-list cap and the auth headers', async () => {
    mockedListJobs.mockResolvedValue(sampleJobs);
    const { result } = renderHook(() => useJobsStore(), { wrapper: wrapperFor(makeAuthValue()) });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.jobs).toEqual(sampleJobs);
    expect(result.current.error).toBeNull();
    expect(mockedListJobs).toHaveBeenCalledWith(
      { limit: 1000 },
      { 'X-Debug-User-Oid': 'oid-test' },
    );
  });

  it('clears a prior error when a retry begins', async () => {
    mockedListJobs.mockRejectedValueOnce(new Error('network down'));
    const { result } = renderHook(() => useJobsStore(), { wrapper: wrapperFor(makeAuthValue()) });
    await waitFor(() => expect(result.current.error).toBe('network down'));

    // Retry succeeds: error must be cleared (not left set alongside the spinner).
    mockedListJobs.mockResolvedValueOnce(sampleJobs);
    act(() => result.current.refetch());
    await waitFor(() => expect(result.current.jobs).toEqual(sampleJobs));
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error when the initial fetch fails and nothing is cached', async () => {
    mockedListJobs.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useJobsStore(), { wrapper: wrapperFor(makeAuthValue()) });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe('network down');
    expect(result.current.jobs).toEqual([]);
  });

  it('does not fetch when unauthenticated', async () => {
    const authValue = makeAuthValue({ isAuthenticated: false });
    const { result } = renderHook(() => useJobsStore(), { wrapper: wrapperFor(authValue) });

    await Promise.resolve();
    expect(mockedListJobs).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
  });

  it('keeps stale data (and no error) when a background refresh fails', async () => {
    mockedListJobs.mockResolvedValueOnce(sampleJobs);
    const { result } = renderHook(() => useJobsStore(), { wrapper: wrapperFor(makeAuthValue()) });
    await waitFor(() => expect(result.current.jobs).toEqual(sampleJobs));

    mockedListJobs.mockRejectedValueOnce(new Error('flaky'));
    act(() => result.current.refetch());

    await waitFor(() => expect(mockedListJobs).toHaveBeenCalledTimes(2));
    expect(result.current.jobs).toEqual(sampleJobs); // stale data retained
    expect(result.current.error).toBeNull();
  });

  it('patchJob updates a cached job in place', async () => {
    mockedListJobs.mockResolvedValue(sampleJobs);
    const { result } = renderHook(() => useJobsStore(), { wrapper: wrapperFor(makeAuthValue()) });
    await waitFor(() => expect(result.current.jobs).toEqual(sampleJobs));

    act(() => result.current.patchJob('job-1', { is_saved: false }));
    expect(result.current.jobs.find((j) => j.job_id === 'job-1')?.is_saved).toBe(false);
  });
});

describe('derived job views', () => {
  beforeEach(() => {
    mockedListJobs.mockReset();
    mockedListJobs.mockResolvedValue(sampleJobs);
  });

  it('useSavedJobs returns only saved jobs from the shared cache', async () => {
    const { result } = renderHook(() => useSavedJobs(), { wrapper: wrapperFor(makeAuthValue()) });
    await waitFor(() => expect(result.current.jobs.length).toBe(2));
    expect(result.current.jobs.map((j) => j.job_id)).toEqual(['job-1', 'job-3']);
  });

  it('useSavedJobs drops a cancelled scan even when it is still flagged saved', async () => {
    // A cancelled scan is one the user deliberately stopped, so it must not linger in the
    // cookbook, whatever its is_saved flag says.
    mockedListJobs.mockResolvedValue([
      makeJob({ job_id: 'job-1', is_saved: true }),
      makeJob({ job_id: 'job-cancelled', is_saved: true, status: 'Cancelled' }),
    ]);
    const { result } = renderHook(() => useSavedJobs(), { wrapper: wrapperFor(makeAuthValue()) });
    await waitFor(() => expect(result.current.jobs.length).toBe(1));
    expect(result.current.jobs.map((j) => j.job_id)).toEqual(['job-1']);
  });
});
