import styles from './SplashScreen.module.css';

/**
 * The boot splash: "the flame ignites." A single gold spark catches, blooms into
 * candlelight that lights the wordmark from within, then settles into a slow candle
 * flicker that loops until the boot gate (AppBootGate) reveals the app, so it holds
 * gracefully whether the load is instant or a cold start.
 *
 * Purely presentational; the gate owns timing. Honors prefers-reduced-motion by
 * showing the fully-lit scene with no ignition or flicker. The medallion, wordmark,
 * and tagline mirror the splash Logo so the brand mark stays consistent.
 */
export function SplashScreen() {
  return (
    <div className={styles.screen}>
      <div className={styles.vignette} aria-hidden="true" />
      <div className={styles.stage}>
        <div className={styles.bloom} aria-hidden="true" />
        <div className={styles.mark} aria-hidden="true">
          R
        </div>
        <div className={styles.textBlock}>
          <div className={styles.wordmark}>REPLATE</div>
          <div className={styles.tagline}>reverse-engineer any dish</div>
        </div>
      </div>
    </div>
  );
}
