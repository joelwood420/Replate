import type { MatchMethod } from '../lib/apiClient';
import styles from './ConfidenceBadge.module.css';

// No mock exists for the non-menu-matched states - this is a judgment-call extension so a
// real menu match reads differently from an unaided vision guess (the pipeline's
// anti-hallucination signal per CLAUDE.md shouldn't be hidden in the UI).
const COPY: Record<MatchMethod, { text: string; showCheck: boolean }> = {
  menu_matched: { text: 'Cross-checked with menu', showCheck: true },
  vision_only_medium: { text: 'AI estimate', showCheck: false },
  vision_only_low: { text: 'Unmatched — AI estimate', showCheck: false },
};

export function ConfidenceBadge({ matchMethod }: { matchMethod: MatchMethod }) {
  const copy = COPY[matchMethod];
  const variant = matchMethod === 'menu_matched' ? styles.matched : styles.unmatched;

  return (
    <div className={`${styles.badge} ${variant}`}>
      {copy.showCheck && <span className={styles.check}>✓</span>}
      <span>{copy.text}</span>
    </div>
  );
}
