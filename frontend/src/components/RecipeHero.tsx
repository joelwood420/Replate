import type { MatchMethod } from '../lib/apiClient';
import { ConfidenceBadge } from './ConfidenceBadge';
import styles from './RecipeHero.module.css';

function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M6 6l1 14a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-14" />
    </svg>
  );
}

interface RecipeHeroProps {
  imageUrl: string;
  dishName: string;
  restaurantMeta: string;
  matchMethod: MatchMethod;
  mode: 'new' | 'cookbook';
  isSaved: boolean;
  onBack: () => void;
  onToggleSaved: () => void;
}

export function RecipeHero({
  imageUrl,
  dishName,
  restaurantMeta,
  matchMethod,
  mode,
  isSaved,
  onBack,
  onToggleSaved,
}: RecipeHeroProps) {
  return (
    <div className={styles.hero}>
      <img src={imageUrl} alt={dishName} className={styles.image} />
      <div className={styles.scrim} />
      <button type="button" className={styles.back} onClick={onBack} aria-label="Back">
        ←
      </button>
      {mode === 'cookbook' && (
        <button
          type="button"
          className={styles.remove}
          onClick={onToggleSaved}
          aria-label={isSaved ? 'Remove from cookbook' : 'Add to cookbook'}
        >
          {isSaved ? <TrashIcon /> : '＋'}
        </button>
      )}
      <div className={styles.overlayText}>
        <ConfidenceBadge matchMethod={matchMethod} />
        <div className={styles.title}>{dishName}</div>
        <div className={styles.meta}>{restaurantMeta}</div>
      </div>
    </div>
  );
}
