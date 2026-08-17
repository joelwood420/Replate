import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { useAuth } from '../lib/auth/useAuth';
import styles from './SplashScreen.module.css';

// Long enough for the logo to fade in, hold, and fade back out (see the `.logo`
// animation in the stylesheet) before we route on. Keep the two in step.
const SPLASH_DURATION_MS = 2400;

export function SplashScreen() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    const timer = setTimeout(() => {
      // Already-signed-in users skip the login page entirely and land on Home.
      navigate(isAuthenticated ? '/home' : '/signin', { replace: true });
    }, SPLASH_DURATION_MS);
    return () => clearTimeout(timer);
  }, [isAuthenticated, navigate]);

  return (
    <div className={styles.screen}>
      <div className={styles.logo}>
        <Logo variant="splash" />
      </div>
    </div>
  );
}
