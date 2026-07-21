import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { useAuth } from '../lib/auth/useAuth';
import styles from './SplashScreen.module.css';

const SPLASH_DELAY_MS = 900;

export function SplashScreen() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    const timer = setTimeout(() => {
      navigate(isAuthenticated ? '/home' : '/signin', { replace: true });
    }, SPLASH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [isAuthenticated, navigate]);

  return (
    <div className={styles.screen}>
      <Logo variant="splash" />
    </div>
  );
}
