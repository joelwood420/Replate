import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { JobSummary } from '../lib/apiClient';
import { ProcessingOrb } from './ProcessingOrb';
import { IconPlus, IconTrash } from './icons';
import styles from './CookbookCard.module.css';

interface CookbookCardProps {
  job: JobSummary;
  onToggleSaved: (jobId: string, saved: boolean) => void;
}

export function CookbookCard({ job, onToggleSaved }: CookbookCardProps) {
  // A photo whose object was purged (or never loaded) should fall back to the striped
  // placeholder, never the browser's broken-image glyph.
  const [imgFailed, setImgFailed] = useState(false);
  const inFlight = job.status === 'Queued' || job.status === 'Processing';
  const failed = job.status === 'Failed';
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
        {/* A settled, saved dish is the only card you remove. While a scan is in flight or has
            failed it isn't a keepable dish yet (Cancel lives on the processing screen), so the
            add/remove control would only confuse - hide it. */}
        {!inFlight && !failed && (
          <button
            type="button"
            className={styles.remove}
            onClick={() => onToggleSaved(job.job_id, !job.is_saved)}
            aria-label={job.is_saved ? 'Remove from cookbook' : 'Add to cookbook'}
          >
            {job.is_saved ? <IconTrash size={12} /> : <IconPlus size={13} />}
          </button>
        )}
        {job.status === 'Identified' && <div className={styles.pendingBadge}>Not yet reverse-engineered</div>}
      </div>
      <div className={`${styles.name} ${failed ? styles.nameFailed : ''}`}>{displayName}</div>
      <div className={styles.place}>{job.restaurant_name ?? ''}</div>
    </div>
  );
}
