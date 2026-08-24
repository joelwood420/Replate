import { PillButton } from './PillButton';
import styles from './ScanCard.module.css';

export function ScanCard({
  onOpenCamera,
  onUploadPhoto,
}: {
  onOpenCamera: () => void;
  onUploadPhoto: () => void;
}) {
  return (
    <div className={styles.card}>
      <div className={styles.iconCircle}>
        <div className={styles.cameraBody}>
          <div className={styles.cameraViewfinder} />
        </div>
      </div>
      <div className={styles.title}>Scan a Dish</div>
      <div className={styles.description}>
        Photograph your plate — Replate finds the restaurant, cross-checks the menu, and
        reverse-engineers the recipe.
      </div>
      <PillButton variant="cta" className={styles.button} onClick={onOpenCamera}>
        Open Camera
      </PillButton>
      <button type="button" className={styles.uploadLink} onClick={onUploadPhoto}>
        Upload a photo instead
      </button>
    </div>
  );
}
