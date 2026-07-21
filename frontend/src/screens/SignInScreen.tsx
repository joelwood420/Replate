import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { useAuth } from '../lib/auth/useAuth';
import styles from './SignInScreen.module.css';

export function SignInScreen() {
  const { signIn, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Reactive rather than navigating right after calling signIn(): the mock provider
  // authenticates synchronously, but the real MSAL provider's loginRedirect() is async
  // (and hands the whole page over to a redirect) - this handles both uniformly.
  useEffect(() => {
    if (isAuthenticated) navigate('/home', { replace: true });
  }, [isAuthenticated, navigate]);

  return (
    <div className={styles.screen}>
      <Logo variant="signin" />
      <div className={styles.subtext}>Sign in with your organization account to continue</div>
      <div className={styles.spacer} />
      <div className={styles.actions}>
        <button type="button" className={styles.msButton} onClick={signIn}>
          <span className={styles.msGlyph}>
            <span className={styles.msRed} />
            <span className={styles.msGreen} />
            <span className={styles.msBlue} />
            <span className={styles.msYellow} />
          </span>
          <span>Sign in with Microsoft</span>
        </button>
        <div className={styles.finePrint}>
          Authenticated via Microsoft Entra ID. Your credentials are never stored by Replate.
        </div>
      </div>
    </div>
  );
}
