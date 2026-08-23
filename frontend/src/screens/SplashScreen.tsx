import { Logo } from '../components/Logo';
import styles from './SplashScreen.module.css';

/**
 * The boot splash. Purely presentational now: the app boot gate (AppBootGate)
 * decides when it shows and when it gives way to the app, so this no longer holds
 * a timer or routes anywhere. The logo fades in and holds until the gate unmounts it.
 */
export function SplashScreen() {
  return (
    <div className={styles.screen}>
      <div className={styles.logo}>
        <Logo variant="splash" />
      </div>
    </div>
  );
}
