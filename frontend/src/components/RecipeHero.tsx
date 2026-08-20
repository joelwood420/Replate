import type { MatchMethod } from '../lib/apiClient';
import { ConfidenceBadge } from './ConfidenceBadge';
import { IconBack, IconPlus, IconTrash } from './icons';
import styles from './RecipeHero.module.css';

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
        <IconBack size={16} />
      </button>
      {mode === 'cookbook' && (
        <button
          type="button"
          className={styles.remove}
          onClick={onToggleSaved}
          aria-label={isSaved ? 'Remove from cookbook' : 'Add to cookbook'}
        >
          {isSaved ? <IconTrash size={15} /> : <IconPlus size={16} />}
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
