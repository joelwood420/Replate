import styles from './ComponentCard.module.css';

export function ComponentCard({ role, name }: { role: string | null; name: string }) {
  return (
    <div className={styles.card}>
      <div className={styles.role}>{role ?? 'Component'}</div>
      <div className={styles.name}>{name}</div>
    </div>
  );
}
