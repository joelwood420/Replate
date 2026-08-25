import { Link } from 'react-router-dom';
import type { JobSummary } from '../lib/apiClient';
import { IconPlus, IconTrash } from './icons';
import styles from './CookbookCard.module.css';

interface CookbookCardProps {
  job: JobSummary;
  onToggleSaved: (jobId: string, saved: boolean) => void;
}

export function CookbookCard({ job, onToggleSaved }: CookbookCardProps) {
  return (
    <div className={styles.card}>
      <div className={styles.thumbWrap}>
        <Link to={`/jobs/${job.job_id}`} className={styles.thumbLink}>
          <div className={styles.thumb}>
            {job.image_url && <img src={job.image_url} alt="" className={styles.thumbImg} />}
          </div>
        </Link>
        <button
          type="button"
          className={styles.remove}
          onClick={() => onToggleSaved(job.job_id, !job.is_saved)}
          aria-label={job.is_saved ? 'Remove from cookbook' : 'Add to cookbook'}
        >
          {job.is_saved ? <IconTrash size={12} /> : <IconPlus size={13} />}
        </button>
        {(job.status === 'Queued' || job.status === 'Processing') && (
          <div className={`${styles.pendingBadge} ${styles.processingBadge}`}>
            <span className={styles.pulse} aria-hidden="true" />
            Processing
          </div>
        )}
        {job.status === 'Identified' && <div className={styles.pendingBadge}>Not yet reverse-engineered</div>}
      </div>
      <div className={styles.name}>{job.dish_name ?? 'Identifying…'}</div>
      <div className={styles.place}>{job.restaurant_name ?? ''}</div>
    </div>
  );
}
