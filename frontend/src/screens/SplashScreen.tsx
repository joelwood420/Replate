import styles from './SplashScreen.module.css';

/**
 * The boot splash: "the flame ignites." A single gold spark catches, blooms into
 * candlelight that lights the wordmark from within, then settles into a slow candle
 * flicker that loops until the boot gate (AppBootGate) reveals the app, so it holds
 * gracefully whether the load is instant or a cold start.
 *
 * When the gate signals `exiting`, the candlelight hands off to the room: the bloom
 * flares wide, the medallion and wordmark recede into the brightness, and the whole
 * layer dissolves to reveal the app mounted behind it — the flame that was the only
 * light in the room opening up to unveil it, instead of a hard cut.
 *
 * Purely presentational; the gate owns timing. Honors prefers-reduced-motion by
 * showing the fully-lit scene with no ignition or flicker (and a plain cross-fade on
 * exit). The medallion, wordmark, and tagline mirror the splash Logo so the brand
 * mark stays consistent.
 */
export function SplashScreen({ exiting = false }: { exiting?: boolean }) {
  return (
    <div className={`${styles.screen}${exiting ? ` ${styles.exiting}` : ''}`}>
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
