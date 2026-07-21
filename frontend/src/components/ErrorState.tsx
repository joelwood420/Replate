import { PillButton } from './PillButton';
import styles from './ErrorState.module.css';

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.message}>{message}</div>
      {onRetry && (
        <PillButton variant="cta" onClick={onRetry}>
          Try again
        </PillButton>
      )}
    </div>
  );
}
