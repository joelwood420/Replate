import { useNavigate } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { BottomTabBar } from '../components/BottomTabBar';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { RecentJobRow } from '../components/RecentJobRow';
import { ScanCard } from '../components/ScanCard';
import { useAuth } from '../lib/auth/useAuth';
import { useRecentJobs } from '../lib/jobs/useRecentJobs';
import { TAB_ROUTES, useSwipeEntryClass, useSwipeNavigation } from '../lib/nav/swipeNav';
import styles from './HomeScreen.module.css';

function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function HomeScreen() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { jobs, isLoading, error, refetch } = useRecentJobs();
  useSwipeNavigation(TAB_ROUTES);
  const swipeEntry = useSwipeEntryClass();

  return (
    <div className={`${styles.screen} ${swipeEntry}`}>
      <div className={styles.header}>
        <div>
          <div className={styles.greeting}>{timeGreeting()}</div>
          <div className={styles.name}>{user?.name.split(' ')[0] ?? 'there'}</div>
        </div>
        <Avatar initials={user?.initials ?? ''} />
      </div>

      <div className={styles.scanWrap}>
        <ScanCard onOpenCamera={() => navigate('/capture')} />
      </div>

      <div className={styles.recentSection}>
        <div className={styles.sectionLabel}>Recently Identified</div>
        {isLoading && <LoadingState label="Loading your dishes…" />}
        {error && <ErrorState message={error} onRetry={refetch} />}
        {!isLoading && !error && jobs.length === 0 && (
          <div className={styles.empty}>No dishes identified yet — scan your first plate.</div>
        )}
        {!isLoading && !error && jobs.length > 0 && (
          <div className={styles.recentList}>
            {jobs.map((job) => (
              <RecentJobRow key={job.job_id} job={job} />
            ))}
          </div>
        )}
      </div>

      <BottomTabBar active="home" />
    </div>
  );
}
