import { PillButton } from './PillButton';
import styles from './ErrorState.module.css';

interface ErrorAction {
  label: string;
  onClick: () => void;
}

type ErrorTone = 'error' | 'moderation' | 'notice';

interface ErrorStateProps {
  message: string;
  /** When present, the component renders its full-screen treatment: a gold medallion,
   *  a serif title, and a stacked primary/secondary action set. Omitted (the inline
   *  callers on Home/Cookbook/Capture) keeps the compact message + retry shape. */
  title?: string;
  tone?: ErrorTone;
  /** Back-compat convenience: renders a primary "Try again" pill. `primaryAction` wins
   *  when both are supplied. */
  onRetry?: () => void;
  retryLabel?: string;
  primaryAction?: ErrorAction;
  secondaryAction?: ErrorAction;
}

function ToneGlyph({ tone }: { tone: ErrorTone }) {
  if (tone === 'moderation') {
    // A camera — echoes the "take another photo" recovery this tone always offers.
    return (
      <svg
        width="26"
        height="22"
        viewBox="0 0 26 22"
        fill="none"
        stroke="var(--color-gold)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="1" y="5" width="24" height="15" rx="3" />
        <path d="M9 5 8.4 2.6A1.2 1.2 0 0 1 9.6 1.4h6.8a1.2 1.2 0 0 1 1.2 1.2L18 5" />
        <circle cx="13" cy="12.5" r="4" />
      </svg>
    );
  }
  // error / notice — a quiet exclamation.
  return (
    <svg
      width="20"
      height="24"
      viewBox="0 0 20 24"
      fill="none"
      stroke="var(--color-gold)"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M10 4 v9.5" />
      <circle cx="10" cy="18.8" r="0.7" fill="var(--color-gold)" stroke="none" />
    </svg>
  );
}

export function ErrorState({
  message,
  title,
  tone = 'error',
  onRetry,
  retryLabel = 'Try again',
  primaryAction,
  secondaryAction,
}: ErrorStateProps) {
  const primary = primaryAction ?? (onRetry ? { label: retryLabel, onClick: onRetry } : undefined);
  const showMedallion = Boolean(title);

  return (
    <div className={styles.wrap} role="alert">
      {showMedallion && (
        <span className={styles.medallion}>
          <ToneGlyph tone={tone} />
        </span>
      )}
      {title && <h2 className={styles.title}>{title}</h2>}
      <p className={styles.message}>{message}</p>
      {(primary || secondaryAction) && (
        <div className={styles.actions}>
          {primary && (
            <PillButton variant="cta" onClick={primary.onClick}>
              {primary.label}
            </PillButton>
          )}
          {secondaryAction && (
            <button type="button" className={styles.ghost} onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
