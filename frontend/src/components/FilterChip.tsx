import styles from './FilterChip.module.css';

interface FilterChipProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

export function FilterChip({ label, active, onClick }: FilterChipProps) {
  return (
    <button type="button" onClick={onClick} className={`${styles.chip} ${active ? styles.active : styles.inactive}`}>
      {label}
    </button>
  );
}
