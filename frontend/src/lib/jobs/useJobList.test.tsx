import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { AuthWrapper, makeAuthValue } from '../../test/renderWithAuth';
import type { JobSummary } from '../apiClient';
import { useJobList } from './useJobList';

vi.mock('../apiClient', () => ({
  listJobs: vi.fn(),
}));

import { listJobs } from '../apiClient';

const mockedListJobs = vi.mocked(listJobs);

const sampleJobs: JobSummary[] = [
  {
    job_id: 'job-1',
    status: 'Completed',
    is_saved: true,
    created_at: '2026-08-22T10:00:00.000Z',
    dish_name: 'Cacio e pepe',
    restaurant_name: 'Trattoria',
    image_url: 'https://example.test/1.jpg',
  },
];

describe('useJobList', () => {
  beforeEach(() => {
    mockedListJobs.mockReset();
  });

  it('loads jobs for an authenticated user', async () => {
    mockedListJobs.mockResolvedValue(sampleJobs);
    const authValue = makeAuthValue();

    const { result } = renderHook(() => useJobList({ limit: 5 }), {
      wrapper: ({ children }) => <AuthWrapper value={authValue}>{children}</AuthWrapper>,
    });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.jobs).toEqual(sampleJobs);
    expect(result.current.error).toBeNull();
    expect(mockedListJobs).toHaveBeenCalledWith({ limit: 5 }, { 'X-Debug-User-Oid': 'oid-test' });
  });

  it('surfaces an error message when the fetch fails', async () => {
    mockedListJobs.mockRejectedValue(new Error('network down'));
    const authValue = makeAuthValue();

    const { result } = renderHook(() => useJobList({ saved: true }), {
      wrapper: ({ children }) => <AuthWrapper value={authValue}>{children}</AuthWrapper>,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe('network down');
    expect(result.current.jobs).toEqual([]);
  });

  it('does not fetch when unauthenticated', async () => {
    const authValue = makeAuthValue({ isAuthenticated: false });
    const { result } = renderHook(() => useJobList({}), {
      wrapper: ({ children }) => <AuthWrapper value={authValue}>{children}</AuthWrapper>,
    });

    // refetch() returns early, so listJobs is never called and loading never resolves.
    await Promise.resolve();
    expect(mockedListJobs).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(true);
  });
});
