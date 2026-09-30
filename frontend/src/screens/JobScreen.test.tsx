import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthContext } from '../lib/auth/AuthProvider';
import { makeAuthValue } from '../test/renderWithAuth';
import type { JobDetail } from '../lib/apiClient';
import { JobScreen } from './JobScreen';

vi.mock('../lib/jobs/useJobPolling', () => ({ useJobPolling: vi.fn() }));
vi.mock('../lib/jobs/JobsProvider', () => ({ useJobsStore: () => ({ removeJob: vi.fn() }) }));

import { useJobPolling } from '../lib/jobs/useJobPolling';

const mockedPolling = vi.mocked(useJobPolling);

function failedJob(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    job_id: 'job-1',
    status: 'Failed',
    image_url: 'https://example.com/p.jpg',
    is_saved: false,
    created_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

function renderWithJob(job: JobDetail) {
  mockedPolling.mockReturnValue({ job, error: null, isLoading: false, refetch: vi.fn() } as never);
  return render(
    <MemoryRouter initialEntries={['/jobs/job-1']}>
      <AuthContext.Provider value={makeAuthValue()}>
        <Routes>
          <Route path="/jobs/:jobId" element={<JobScreen />} />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe('JobScreen failed states', () => {
  beforeEach(() => mockedPolling.mockReset());

  it('shows the not-food message for a not_food failure', () => {
    renderWithJob(failedJob({ failure_code: 'not_food', error_message: 'That looks like a cat.' }));

    expect(screen.getByText("That doesn't look like food")).toBeInTheDocument();
    expect(screen.getByText('That looks like a cat.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /take another photo/i })).toBeInTheDocument();
  });

  it('keeps the generic copy for other failures', () => {
    renderWithJob(failedJob({ error_message: 'boom' }));

    expect(screen.getByText("That scan didn't work")).toBeInTheDocument();
    expect(screen.queryByText("That doesn't look like food")).not.toBeInTheDocument();
  });
});
