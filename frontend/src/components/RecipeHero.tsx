import type { MatchMethod } from '../lib/apiClient';
import { ConfidenceBadge } from './ConfidenceBadge';
import { IconBack, IconTrash } from './icons';
import styles from './RecipeHero.module.css';

interface RecipeHeroProps {
  imageUrl: string;
  dishName: string;
  restaurantMeta: string;
  matchMethod: MatchMethod;
  mode: 'new' | 'cookbook';
  onBack: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

export function RecipeHero({
  imageUrl,
  dishName,
  restaurantMeta,
  matchMethod,
  mode,
  onBack,
  onDelete,
  isDeleting,
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
          onClick={onDelete}
          disabled={isDeleting}
          aria-label="Delete dish"
        >
          <IconTrash size={15} />
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
