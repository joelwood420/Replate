import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { useAuth } from '../lib/auth/useAuth';
import styles from './OnboardingScreen.module.css';

// Mirrors the user pool's password policy (infra/template.yaml) so we fail fast in the
// form instead of round-tripping to Cognito for an InvalidPasswordException.
function passwordProblem(password: string): string | null {
  if (password.length < 8) return 'Password must be at least 8 characters.';
  if (!/[a-z]/.test(password)) return 'Password needs a lowercase letter.';
  if (!/[A-Z]/.test(password)) return 'Password needs an uppercase letter.';
  if (!/\d/.test(password)) return 'Password needs a number.';
  return null;
}

export function OnboardingScreen() {
  const { signUp, confirmSignUp, resendConfirmationCode, signIn, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<'form' | 'verify'>('form');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isAuthenticated) navigate('/home', { replace: true });
  }, [isAuthenticated, navigate]);

  const canSubmitForm =
    name.trim().length > 0 && email.trim().length > 0 && password.length > 0 && !busy;
  const canSubmitCode = /^\d{6}$/.test(code) && !busy;

  async function handleSignUp(event: FormEvent) {
    event.preventDefault();
    if (!canSubmitForm) return;
    const pwProblem = passwordProblem(password);
    if (pwProblem) {
      setError(pwProblem);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const { needsConfirmation } = await signUp({ name: name.trim(), email: email.trim(), password });
      if (needsConfirmation) {
        setPhase('verify');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create your account.');
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify(event: FormEvent) {
    event.preventDefault();
    if (!canSubmitCode) return;
    setError(null);
    setBusy(true);
    try {
      await confirmSignUp(email.trim(), code.trim());
      // Confirmation doesn't establish a session, so log the new user straight in.
      await signIn(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not verify your account.');
      setBusy(false);
    }
  }

  async function handleResend() {
    setError(null);
    try {
      await resendConfirmationCode(email.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resend the code.');
    }
  }

  if (phase === 'verify') {
    return (
      <div className={styles.screen}>
        <Logo variant="signin" />
        <div className={styles.subtext}>
          Enter the 6-digit code we sent to <span className={styles.emphasis}>{email.trim()}</span>
        </div>

        <form className={styles.form} onSubmit={handleVerify}>
          <label className={styles.field}>
            <span className={styles.label}>Verification code</span>
            <input
              type="text"
              inputMode="numeric"
              className={styles.input}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456"
              autoComplete="one-time-code"
              autoFocus
            />
          </label>

          {error && <div className={styles.error}>{error}</div>}

          <button type="submit" className={styles.primaryButton} disabled={!canSubmitCode}>
            {busy ? 'Verifying…' : 'Verify & continue'}
          </button>
        </form>

        <button type="button" className={styles.backLink} onClick={handleResend}>
          Didn’t get it? Resend code
        </button>
      </div>
    );
  }

  return (
    <div className={styles.screen}>
      <Logo variant="signin" />
      <div className={styles.subtext}>Create your account</div>

      <form className={styles.form} onSubmit={handleSignUp}>
        <label className={styles.field}>
          <span className={styles.label}>Your name</span>
          <input
            type="text"
            className={styles.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Elena Marchetti"
            autoComplete="name"
            autoFocus
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Email</span>
          <input
            type="email"
            className={styles.input}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Password</span>
          <input
            type="password"
            className={styles.input}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            autoComplete="new-password"
          />
        </label>

        {error && <div className={styles.error}>{error}</div>}

        <button type="submit" className={styles.primaryButton} disabled={!canSubmitForm}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
      </form>

      <div className={styles.divider}>
        <span className={styles.dividerLine} />
        <span className={styles.dividerText}>or</span>
        <span className={styles.dividerLine} />
      </div>

      {/* Placeholder: Google sign-in is not wired up yet. */}
      <button type="button" className={styles.googleButton}>
        Continue with Google
      </button>

      <div className={styles.spacer} />

      <button type="button" className={styles.backLink} onClick={() => navigate('/signin')}>
        Already have an account? Log in
      </button>
    </div>
  );
}
