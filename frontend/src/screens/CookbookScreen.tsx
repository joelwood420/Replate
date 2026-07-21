import { useState } from 'react';
import { BottomTabBar } from '../components/BottomTabBar';
import { CookbookCard } from '../components/CookbookCard';
import { ErrorState } from '../components/ErrorState';
import { FilterChip } from '../components/FilterChip';
import { LoadingState } from '../components/LoadingState';
import { setJobSaved } from '../lib/apiClient';
import { useAuth } from '../lib/auth/useAuth';
import { useSavedJobs } from '../lib/jobs/useSavedJobs';
import styles from './CookbookScreen.module.css';

const FILTERS = ['All', 'Mains', 'Sauces', 'Desserts'];

export function CookbookScreen() {
  const { authHeaders } = useAuth();
  const { jobs, isLoading, error, refetch } = useSavedJobs();
  const [activeFilter, setActiveFilter] = useState('All');

  // Filter chips beyond "All" have no backing category field on the backend yet
  // (JobResults.Cuisine isn't the same as a component-type category) - "All" is the
  // only chip guaranteed meaningful until a real category field exists.
  const visibleJobs = jobs;

  async function handleToggleSaved(jobId: string, saved: boolean) {
    await setJobSaved(jobId, saved, authHeaders);
    refetch();
  }

  return (
    <div className={styles.screen}>
      <div className={styles.header}>
        <div className={styles.title}>My Cookbook</div>
        <div className={styles.subhead}>{jobs.length} recipes reverse-engineered</div>
      </div>

      <div className={styles.filters}>
        {FILTERS.map((label) => (
          <FilterChip
            key={label}
            label={label}
            active={activeFilter === label}
            onClick={() => setActiveFilter(label)}
          />
        ))}
      </div>

      <div className={styles.body}>
        {isLoading && <LoadingState label="Loading your cookbook…" />}
        {error && <ErrorState message={error} onRetry={refetch} />}
        {!isLoading && !error && visibleJobs.length === 0 && (
          <div className={styles.empty}>Nothing saved yet — tap the heart on a recipe to add it here.</div>
        )}
        {!isLoading && !error && visibleJobs.length > 0 && (
          <div className={styles.grid}>
            {visibleJobs.map((job) => (
              <CookbookCard key={job.job_id} job={job} onToggleSaved={handleToggleSaved} />
            ))}
          </div>
        )}
      </div>

      <BottomTabBar active="saved" />
    </div>
  );
}
