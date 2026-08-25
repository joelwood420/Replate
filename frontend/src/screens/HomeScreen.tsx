import { useRef } from 'react';
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
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    // Uploads have their own screen, separate from the camera: it takes location from the
    // photo's EXIF (or a manual restaurant search) and never opens the camera or asks for
    // device location. See docs/decisions.md.
    navigate('/upload', { state: { uploadedFile: file } });
  }

  return (
    <div className={`${styles.screen} ${swipeEntry}`}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileSelected}
        className={styles.hiddenFileInput}
      />
      <div className={styles.header}>
        <div>
          <div className={styles.greeting}>{timeGreeting()}</div>
          <div className={styles.name}>{user?.name.split(' ')[0] ?? 'there'}</div>
        </div>
        <Avatar initials={user?.initials ?? ''} />
      </div>

      <div className={styles.scanWrap}>
        <ScanCard
          onOpenCamera={() => navigate('/capture')}
          onUploadPhoto={() => fileInputRef.current?.click()}
        />
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
