import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthContext } from '../lib/auth/AuthProvider';
import { makeAuthValue } from '../test/renderWithAuth';
import { EditProfileScreen } from './EditProfileScreen';

vi.mock('../lib/apiClient', () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
}));

import { getProfile, updateProfile } from '../lib/apiClient';

const mockedGetProfile = vi.mocked(getProfile);
const mockedUpdateProfile = vi.mocked(updateProfile);

function renderScreen(authValue = makeAuthValue()) {
  return render(
    <MemoryRouter initialEntries={['/profile/edit']}>
      <AuthContext.Provider value={authValue}>
        <Routes>
          <Route path="/profile/edit" element={<EditProfileScreen />} />
          <Route path="/profile" element={<div>Profile Screen</div>} />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe('EditProfileScreen', () => {
  beforeEach(() => {
    mockedGetProfile.mockReset();
    mockedUpdateProfile.mockReset();
  });

  it('prefills the display name from the profile and disables Save until it changes', async () => {
    mockedGetProfile.mockResolvedValue({
      display_name: 'Amara Silva',
      email: 'amara@example.com',
      created_at: '2026-01-01T00:00:00Z',
    });

    renderScreen();

    const nameInput = await screen.findByDisplayValue('Amara Silva');
    expect(nameInput).toBeInTheDocument();
    expect(screen.getByDisplayValue('amara@example.com')).toBeInTheDocument();
    // Unchanged -> Save disabled.
    expect(screen.getByRole('button', { name: /save changes/i })).toBeDisabled();
  });

  it('falls back to the session name when the profile has none', async () => {
    mockedGetProfile.mockResolvedValue({ display_name: null, email: null, created_at: null });

    renderScreen(makeAuthValue({ user: { name: 'Test Cook', initials: 'TC', oid: 'oid-test' } }));

    expect(await screen.findByDisplayValue('Test Cook')).toBeInTheDocument();
  });

  it('saves the trimmed name, syncs the session, and returns to the profile', async () => {
    mockedGetProfile.mockResolvedValue({
      display_name: 'Amara',
      email: 'amara@example.com',
      created_at: null,
    });
    mockedUpdateProfile.mockResolvedValue({
      display_name: 'Amara Cooks',
      email: 'amara@example.com',
      created_at: null,
    });
    const updateDisplayName = vi.fn();
    const authValue = makeAuthValue({ updateDisplayName });

    renderScreen(authValue);

    const nameInput = await screen.findByDisplayValue('Amara');
    fireEvent.change(nameInput, { target: { value: '  Amara Cooks  ' } });

    const saveButton = screen.getByRole('button', { name: /save changes/i });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() => expect(mockedUpdateProfile).toHaveBeenCalledWith('Amara Cooks', authValue.authHeaders));
    expect(updateDisplayName).toHaveBeenCalledWith('Amara Cooks');
    expect(await screen.findByText('Profile Screen')).toBeInTheDocument();
  });

  it('surfaces a load error with a retry', async () => {
    mockedGetProfile.mockRejectedValueOnce(new Error('network down'));

    renderScreen();

    expect(await screen.findByText('network down')).toBeInTheDocument();
  });
});
