import { Link } from 'react-router-dom';
import type { JobSummary } from '../lib/apiClient';
import styles from './CookbookCard.module.css';

function TrashIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M6 6l1 14a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-14" />
    </svg>
  );
}

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
          {job.is_saved ? <TrashIcon /> : '＋'}
        </button>
        {job.status === 'Identified' && <div className={styles.pendingBadge}>Not yet reverse-engineered</div>}
      </div>
      <div className={styles.name}>{job.dish_name ?? 'Identifying…'}</div>
      <div className={styles.place}>{job.restaurant_name ?? ''}</div>
    </div>
  );
}
