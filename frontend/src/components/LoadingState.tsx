import styles from './LoadingState.module.css';

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.spinner} />
      <div className={styles.label}>{label}</div>
    </div>
  );
}
