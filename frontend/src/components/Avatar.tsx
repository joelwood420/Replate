import styles from './Avatar.module.css';

export function Avatar({ initials, size = 38 }: { initials: string; size?: number }) {
  return (
    <div className={styles.avatar} style={{ width: size, height: size }}>
      {initials}
    </div>
  );
}
