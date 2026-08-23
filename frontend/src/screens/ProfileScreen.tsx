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

const DIET_OPTIONS = ['Vegetarian', 'Vegan', 'Gluten-free', 'Dairy-free', 'Nut-free'] as const;
type DietOption = (typeof DIET_OPTIONS)[number];
type Units = 'metric' | 'imperial';

interface Prefs {
  diets: DietOption[];
  units: Units;
}

const DEFAULT_PREFS: Prefs = { diets: [], units: 'metric' };

// Preferences live client-side (per user oid) for now — there's no server-side profile
// store in the single-table design yet, so this is the seam for one when it lands.
function prefsKey(oid: string | undefined): string {
  return `replate.prefs.${oid ?? 'anon'}`;
}

function loadPrefs(oid: string | undefined): Prefs {
  try {
    const raw = localStorage.getItem(prefsKey(oid));
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    const diets = Array.isArray(parsed.diets)
      ? parsed.diets.filter((d): d is DietOption => (DIET_OPTIONS as readonly string[]).includes(d))
      : [];
    return { diets, units: parsed.units === 'imperial' ? 'imperial' : 'metric' };
  } catch {
    return DEFAULT_PREFS;
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

  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs(user?.oid));
  useEffect(() => {
    setPrefs(loadPrefs(user?.oid));
  }, [user?.oid]);
  useEffect(() => {
    try {
      localStorage.setItem(prefsKey(user?.oid), JSON.stringify(prefs));
    } catch {
      /* storage unavailable (private mode) — preferences just don't persist */
    }
  }, [prefs, user?.oid]);

  const savedCount = useMemo(() => jobs.filter((job) => job.is_saved).length, [jobs]);
  const streak = useMemo(() => computeDayStreak(jobs.map((job) => job.created_at)), [jobs]);

  const stats: { icon: ReactNode; value: number; label: string }[] = [
    { icon: <IconCamera size={20} />, value: jobs.length, label: 'Dishes' },
    { icon: <IconHeart size={20} />, value: savedCount, label: 'Saved' },
    { icon: <IconFlame size={20} />, value: streak, label: 'Day streak' },
  ];

  function toggleDiet(label: DietOption) {
    setPrefs((prev) => ({
      ...prev,
      diets: prev.diets.includes(label)
        ? prev.diets.filter((d) => d !== label)
        : [...prev.diets, label],
    }));
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
          <div className={styles.sectionLabel}>Dietary preferences</div>
          <div className={styles.chips}>
            {DIET_OPTIONS.map((option) => (
              <FilterChip
                key={option}
                label={option}
                active={prefs.diets.includes(option)}
                onClick={() => toggleDiet(option)}
              />
            ))}
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionLabel}>Measurement units</div>
          <div className={styles.chips}>
            <FilterChip
              label="Metric"
              active={prefs.units === 'metric'}
              onClick={() => setPrefs((prev) => ({ ...prev, units: 'metric' }))}
            />
            <FilterChip
              label="Imperial"
              active={prefs.units === 'imperial'}
              onClick={() => setPrefs((prev) => ({ ...prev, units: 'imperial' }))}
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
