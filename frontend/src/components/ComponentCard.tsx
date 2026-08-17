import styles from './ComponentCard.module.css';

interface ComponentCardProps {
  role: string | null;
  name: string;
  selected?: boolean;
  onClick?: () => void;
}

export function ComponentCard({ role, name, selected = false, onClick }: ComponentCardProps) {
  return (
    <button
      type="button"
      className={`${styles.card} ${selected ? styles.selected : ''}`}
      onClick={onClick}
      aria-pressed={selected}
    >
      <div className={styles.role}>{role ?? 'Component'}</div>
      <div className={styles.name}>{name}</div>
    </button>
  );
}
