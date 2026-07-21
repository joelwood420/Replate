import styles from './CaptureViewfinder.module.css';

export function CaptureViewfinder() {
  return (
    <div className={styles.guide}>
      <span className={`${styles.corner} ${styles.tl}`} />
      <span className={`${styles.corner} ${styles.tr}`} />
      <span className={`${styles.corner} ${styles.bl}`} />
      <span className={`${styles.corner} ${styles.br}`} />
    </div>
  );
}
