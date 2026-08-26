import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { JobSummary } from '../lib/apiClient';
import { ProcessingOrb } from './ProcessingOrb';
import { IconTrash } from './icons';
import styles from './CookbookCard.module.css';

interface CookbookCardProps {
  job: JobSummary;
  onDelete: (jobId: string) => void;
}

export function CookbookCard({ job, onDelete }: CookbookCardProps) {
  // A photo whose object was purged (or never loaded) should fall back to the striped
  // placeholder, never the browser's broken-image glyph.
  const [imgFailed, setImgFailed] = useState(false);
  // The scan is running its stage-1 pipeline: show the orb over the photo.
  const inFlight = job.status === 'Queued' || job.status === 'Processing';
  const failed = job.status === 'Failed';
  // A running job can't be deleted - the backend refuses (409) any non-terminal status,
  // including stage-2 Generating (see job_delete_http.IN_FLIGHT) - so don't offer the control.
  const deletable = !inFlight && job.status !== 'Generating';
  const showImg = job.image_url && !imgFailed;

  const displayName = job.dish_name ?? (inFlight ? 'Identifying…' : failed ? 'Scan failed' : 'Untitled dish');

  return (
    <div className={styles.card}>
      <div className={styles.thumbWrap}>
        <Link to={`/jobs/${job.job_id}`} className={styles.thumbLink}>
          <div className={styles.thumb}>
            {showImg && (
              <img
                src={job.image_url}
                alt=""
                className={styles.thumbImg}
                onError={() => setImgFailed(true)}
              />
            )}
            {inFlight && (
              // The just-scanned photo under a scrim with the orb over it: "your dish, in your
              // cookbook, being worked on" rather than a screen you have to wait on.
              <div className={styles.overlay}>
                <ProcessingOrb compact />
              </div>
            )}
            {failed && (
              <div className={styles.overlay}>
                <div className={styles.failedHint}>Tap to try again</div>
              </div>
            )}
          </div>
        </Link>
        {/* Delete is a hard delete (there is no undo), offered on any settled card - a finished
            dish or a failed scan. A scan still running (stage 1 or stage 2) can't be deleted out
            from under its pipeline; that's what Cancel on the processing screen is for. */}
        {deletable && (
          <button
            type="button"
            className={styles.remove}
            onClick={() => onDelete(job.job_id)}
            aria-label="Delete dish"
          >
            <IconTrash size={12} />
          </button>
        )}
        {job.status === 'Identified' && <div className={styles.pendingBadge}>Not yet reverse-engineered</div>}
      </div>
      <div className={`${styles.name} ${failed ? styles.nameFailed : ''}`}>{displayName}</div>
      <div className={styles.place}>{job.restaurant_name ?? ''}</div>
    </div>
  );
}
