import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ErrorState } from '../components/ErrorState';
import { IconBack } from '../components/icons';
import { LoadingState } from '../components/LoadingState';
import { PillButton } from '../components/PillButton';
import { getProfile, updateProfile } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import styles from './EditProfileScreen.module.css';

const MAX_NAME_LEN = 80;

export function EditProfileScreen() {
  const { user, authHeaders, updateDisplayName } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [initialName, setInitialName] = useState('');
  const [email, setEmail] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(() => {
    setIsLoading(true);
    getProfile(authHeaders)
      .then((profile) => {
        // The stored display name is authoritative; fall back to the session name
        // for a brand-new user whose profile has none yet.
        const current = profile.display_name ?? user?.name ?? '';
        setName(current);
        setInitialName(current);
        setEmail(profile.email);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : 'Failed to load your profile');
      })
      .finally(() => setIsLoading(false));
  }, [authHeaders, user?.name]);

  useEffect(() => {
    load();
  }, [load]);

  const trimmed = name.trim();
  const canSave = trimmed.length > 0 && trimmed.length <= MAX_NAME_LEN && trimmed !== initialName && !saving;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSave) return;
    setSaveError(null);
    setSaving(true);
    try {
      const profile = await updateProfile(trimmed, authHeaders);
      updateDisplayName(profile.display_name ?? trimmed);
      navigate('/profile');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save your changes.');
      setSaving(false);
    }
  }

  return (
    <div className={styles.screen}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.backButton}
          onClick={() => navigate('/profile')}
          aria-label="Back to profile"
        >
          <IconBack size={18} />
        </button>
        <div className={styles.title}>Edit profile</div>
      </div>

      <div className={styles.body}>
        {isLoading && <LoadingState label="Loading your profile…" />}
        {!isLoading && loadError && <ErrorState message={loadError} onRetry={load} />}
        {!isLoading && !loadError && (
          <form className={styles.form} onSubmit={handleSubmit}>
            <label className={styles.field}>
              <span className={styles.label}>Display name</span>
              <input
                type="text"
                className={styles.input}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                maxLength={MAX_NAME_LEN}
                autoComplete="name"
                autoFocus
              />
            </label>

            <label className={styles.field}>
              <span className={styles.label}>Email</span>
              <input
                type="email"
                className={`${styles.input} ${styles.readonly}`}
                value={email ?? ''}
                placeholder="No email on file"
                readOnly
                aria-readonly="true"
              />
              <span className={styles.hint}>Email is tied to your sign-in and can't be changed here.</span>
            </label>

            {saveError && <div className={styles.error}>{saveError}</div>}

            <PillButton variant="footer" type="submit" disabled={!canSave}>
              {saving ? 'Saving…' : 'Save changes'}
            </PillButton>
          </form>
        )}
      </div>
    </div>
  );
}
