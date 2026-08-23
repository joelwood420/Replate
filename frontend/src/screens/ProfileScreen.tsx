import { useEffect, useMemo, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { BottomTabBar } from '../components/BottomTabBar';
import {
  IconBell,
  IconCamera,
  IconChevron,
  IconEdit,
  IconFlame,
  IconHeart,
  IconHelp,
} from '../components/icons';
import { useAuth } from '../lib/auth/useAuth';
import { computeDayStreak } from '../lib/format';
import { useJobsStore } from '../lib/jobs/JobsProvider';
import { TAB_ROUTES, useSwipeEntryClass, useSwipeNavigation } from '../lib/nav/swipeNav';
import styles from './ProfileScreen.module.css';

export function ProfileScreen() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { jobs, refetch } = useJobsStore();
  useSwipeNavigation(TAB_ROUTES);
  const swipeEntry = useSwipeEntryClass();

  useEffect(() => {
    refetch();
  }, [refetch]);

  const savedCount = useMemo(() => jobs.filter((job) => job.is_saved).length, [jobs]);
  const streak = useMemo(() => computeDayStreak(jobs.map((job) => job.created_at)), [jobs]);

  const stats: { icon: ReactNode; value: number; label: string }[] = [
    { icon: <IconCamera size={20} />, value: jobs.length, label: 'Dishes' },
    { icon: <IconHeart size={20} />, value: savedCount, label: 'Saved' },
    { icon: <IconFlame size={20} />, value: streak, label: 'Day streak' },
  ];

  // A row with an onClick is interactive (rendered as a button); the rest are
  // presentational placeholders until their destination screens land.
  const accountRows: {
    icon: ReactNode;
    title: string;
    sub?: string;
    value?: string;
    onClick?: () => void;
  }[] = [
    {
      icon: <IconEdit size={18} />,
      title: 'Edit profile',
      sub: 'Name, photo, email',
      onClick: () => navigate('/profile/edit'),
    },
    { icon: <IconBell size={18} />, title: 'Notifications', value: 'On' },
    { icon: <IconHelp size={18} />, title: 'Help & feedback' },
  ];

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
          <div className={styles.sectionLabel}>Account</div>
          <div className={styles.list}>
            {accountRows.map((row) => {
              const inner = (
                <>
                  <div className={styles.rowIcon}>{row.icon}</div>
                  <div className={styles.rowText}>
                    <div className={styles.rowTitle}>{row.title}</div>
                    {row.sub && <div className={styles.rowSub}>{row.sub}</div>}
                  </div>
                  {row.value && <div className={styles.rowValue}>{row.value}</div>}
                  <div className={styles.rowChevron}>
                    <IconChevron size={16} />
                  </div>
                </>
              );
              return row.onClick ? (
                <button key={row.title} type="button" className={styles.row} onClick={row.onClick}>
                  {inner}
                </button>
              ) : (
                <div key={row.title} className={styles.row}>
                  {inner}
                </div>
              );
            })}
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
