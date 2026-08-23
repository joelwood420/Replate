import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { BottomTabBar } from '../components/BottomTabBar';
import { FilterChip } from '../components/FilterChip';
import { IconCamera, IconFlame, IconHeart } from '../components/icons';
import { useAuth } from '../lib/auth/useAuth';
import { computeDayStreak } from '../lib/format';
import { useJobsStore } from '../lib/jobs/JobsProvider';
import { TAB_ROUTES, useSwipeEntryClass, useSwipeNavigation } from '../lib/nav/swipeNav';
import styles from './ProfileScreen.module.css';

type Units = 'metric' | 'imperial';

// Preferences live client-side (per user oid) for now; there is no server-side
// profile store in the single-table design yet, so this is the seam for one when
// it lands.
function prefsKey(oid: string | undefined): string {
  return `replate.prefs.${oid ?? 'anon'}`;
}

function loadUnits(oid: string | undefined): Units {
  try {
    const raw = localStorage.getItem(prefsKey(oid));
    if (!raw) return 'metric';
    const parsed = JSON.parse(raw) as { units?: unknown };
    return parsed.units === 'imperial' ? 'imperial' : 'metric';
  } catch {
    return 'metric';
  }
}

export function ProfileScreen() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { jobs, refetch } = useJobsStore();
  useSwipeNavigation(TAB_ROUTES);
  const swipeEntry = useSwipeEntryClass();

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Reload when the signed-in user changes. Persistence is write-through (see
  // chooseUnits), so there is no save effect that could write one user's prefs into
  // another's storage key during an oid change.
  const [units, setUnits] = useState<Units>(() => loadUnits(user?.oid));
  useEffect(() => {
    setUnits(loadUnits(user?.oid));
  }, [user?.oid]);

  const savedCount = useMemo(() => jobs.filter((job) => job.is_saved).length, [jobs]);
  const streak = useMemo(() => computeDayStreak(jobs.map((job) => job.created_at)), [jobs]);

  const stats: { icon: ReactNode; value: number; label: string }[] = [
    { icon: <IconCamera size={20} />, value: jobs.length, label: 'Dishes' },
    { icon: <IconHeart size={20} />, value: savedCount, label: 'Saved' },
    { icon: <IconFlame size={20} />, value: streak, label: 'Day streak' },
  ];

  function chooseUnits(next: Units) {
    setUnits(next);
    try {
      localStorage.setItem(prefsKey(user?.oid), JSON.stringify({ units: next }));
    } catch {
      /* storage unavailable (private mode): the choice just does not persist */
    }
  }

  function handleSignOut() {
    signOut();
    navigate('/signin', { replace: true });
  }

  return (
    <div className={`${styles.screen} ${swipeEntry}`}>
      <div className={styles.header}>
        <div className={styles.label}>Profile</div>
      </div>

      <div className={styles.body}>
        <div className={styles.identity}>
          <Avatar initials={user?.initials ?? ''} size={88} />
          <div className={styles.name}>{user?.name ?? 'there'}</div>
        </div>

        <div className={styles.stats}>
          {stats.map((stat) => (
            <div key={stat.label} className={styles.stat}>
              <div className={styles.statIcon}>{stat.icon}</div>
              <div className={styles.statValue}>{stat.value}</div>
              <div className={styles.statLabel}>{stat.label}</div>
            </div>
          ))}
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>Measurement units</div>
          <div className={styles.chips}>
            <FilterChip
              label="Metric"
              active={units === 'metric'}
              onClick={() => chooseUnits('metric')}
            />
            <FilterChip
              label="Imperial"
              active={units === 'imperial'}
              onClick={() => chooseUnits('imperial')}
            />
          </div>
        </div>
      </div>

      <div className={styles.footer}>
        <button type="button" className={styles.signOutButton} onClick={handleSignOut}>
          Log out
        </button>
      </div>

      <BottomTabBar active="profile" />
    </div>
  );
}
