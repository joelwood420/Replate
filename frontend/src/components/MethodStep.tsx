import styles from './MethodStep.module.css';

export function MethodStep({ number, text }: { number: number; text: string }) {
  return (
    <div className={styles.row}>
      <div className={styles.number}>{number}</div>
      <div className={styles.text}>{text}</div>
    </div>
  );
}
