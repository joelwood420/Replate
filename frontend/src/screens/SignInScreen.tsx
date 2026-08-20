import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { PillButton } from '../components/PillButton';
import { useAuth } from '../lib/auth/useAuth';
import styles from './SignInScreen.module.css';

export function SignInScreen() {
  const { signIn, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Reactive redirect: mock auth resolves synchronously and Cognito after a round
  // trip - watching isAuthenticated handles both uniformly.
  useEffect(() => {
    if (isAuthenticated) navigate('/home', { replace: true });
  }, [isAuthenticated, navigate]);

  const canSubmit = email.trim().length > 0 && password.length > 0 && !busy;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setBusy(true);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in.');
      setBusy(false);
    }
  }

  return (
    <div className={styles.screen}>
      <Logo variant="signin" />
      <div className={styles.subtext}>Welcome back</div>

      <form className={styles.form} onSubmit={handleSubmit}>
        <label className={styles.field}>
          <span className={styles.label}>Email</span>
          <input
            type="email"
            className={styles.input}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            autoFocus
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Password</span>
          <input
            type="password"
            className={styles.input}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your password"
            autoComplete="current-password"
          />
        </label>

        {error && <div className={styles.error}>{error}</div>}

        <PillButton variant="footer" type="submit" disabled={!canSubmit}>
          {busy ? 'Signing in…' : 'Log in'}
        </PillButton>
      </form>

      <div className={styles.spacer} />

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={() => navigate('/onboarding')}
        >
          Create account
        </button>
        <div className={styles.finePrint}>
          Authenticated via Amazon Cognito. Your credentials are never stored by Replate.
        </div>
      </div>
    </div>
  );
}
