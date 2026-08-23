import { useNavigate } from 'react-router-dom';
import { BottomTabBar } from '../components/BottomTabBar';
import { CookbookCard } from '../components/CookbookCard';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { PillButton } from '../components/PillButton';
import { setJobSaved } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useSavedJobs } from '../lib/jobs/useSavedJobs';
import { TAB_ROUTES, useSwipeEntryClass, useSwipeNavigation } from '../lib/nav/swipeNav';
import styles from './CookbookScreen.module.css';

export function CookbookScreen() {
  const { authHeaders } = useAuth();
  const { jobs, isLoading, error, refetch, patchJob } = useSavedJobs();
  const navigate = useNavigate();
  useSwipeNavigation(TAB_ROUTES);
  const swipeEntry = useSwipeEntryClass();

  // Dishes are saved automatically at capture time, so the cookbook holds a mix of
  // reverse-engineered recipes and dishes still waiting to be.
  const reverseEngineered = jobs.filter((job) => job.status === 'Completed').length;
  const summary =
    jobs.length === 0
      ? 'No dishes yet'
      : `${jobs.length} ${jobs.length === 1 ? 'dish' : 'dishes'} · ${reverseEngineered} reverse-engineered`;

  async function handleToggleSaved(jobId: string, saved: boolean) {
    // Update the shared cache first so the card drops/stays instantly; the patch
    // is authoritative for the UI, so there's no immediate refetch. Refetching here
    // would be a full list re-read per toggle and, because list reads are eventually
    // consistent, could momentarily read back the pre-write value and revert the
    // card. A later focus/mount refresh reconciles. Revert only if the write fails.
    patchJob(jobId, { is_saved: saved });
    try {
      await setJobSaved(jobId, saved, authHeaders);
    } catch {
      patchJob(jobId, { is_saved: !saved });
    }
  }

  return (
    <div className={`${styles.screen} ${swipeEntry}`}>
      <div className={styles.header}>
        <div className={styles.title}>My Cookbook</div>
        <div className={styles.subhead}>{summary}</div>
      </div>

      <div className={styles.body}>
        {isLoading && <LoadingState label="Loading your cookbook…" />}
        {error && <ErrorState message={error} onRetry={refetch} />}
        {!isLoading && !error && jobs.length === 0 && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <svg
                width="30"
                height="30"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5.5 3H19a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H5.5A1.5 1.5 0 0 1 4 18.5v-14A1.5 1.5 0 0 1 5.5 3Z" />
                <path d="M8 3v18" />
                <path d="M12 8h4.5M12 11h4.5" />
              </svg>
            </div>
            <div className={styles.emptyTitle}>Begin your food journey</div>
            <div className={styles.emptyText}>
              Snap a dish and Replate saves it here — your personal cookbook of every plate
              worth recreating.
            </div>
            <PillButton className={styles.emptyCta} onClick={() => navigate('/capture')}>
              Scan your first dish
            </PillButton>
          </div>
        )}
        {!isLoading && !error && jobs.length > 0 && (
          <div className={styles.grid}>
            {jobs.map((job) => (
              <CookbookCard key={job.job_id} job={job} onToggleSaved={handleToggleSaved} />
            ))}
          </div>
        )}
      </div>

      <BottomTabBar active="cookbook" />
    </div>
  );
}
