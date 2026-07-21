import { Link } from 'react-router-dom';
import type { JobSummary } from '../lib/apiClient';
import { timeAgo } from '../lib/format';
import styles from './RecentJobRow.module.css';

export function RecentJobRow({ job }: { job: JobSummary }) {
  const meta = [job.restaurant_name, timeAgo(job.created_at)].filter(Boolean).join(' · ');

  return (
    <Link to={`/jobs/${job.job_id}`} className={styles.row}>
      <div className={styles.thumb}>
        {job.image_url && <img src={job.image_url} alt="" className={styles.thumbImg} />}
      </div>
      <div className={styles.text}>
        <div className={styles.dish}>{job.dish_name ?? 'Identifying…'}</div>
        <div className={styles.meta}>{meta || 'Processing'}</div>
      </div>
      <div className={styles.chevron}>›</div>
    </Link>
  );
}
