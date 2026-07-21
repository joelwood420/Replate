import { Link } from 'react-router-dom';
import styles from './BottomTabBar.module.css';

type Tab = 'home' | 'saved' | 'profile';

// Profile isn't a designed/in-scope screen for Phase 2 - the tab routes to Home rather
// than a dead link or a crash until a Profile screen exists.
const TABS: { key: Tab; label: string; to: string }[] = [
  { key: 'home', label: 'Home', to: '/home' },
  { key: 'saved', label: 'Saved', to: '/cookbook' },
  { key: 'profile', label: 'Profile', to: '/home' },
];

export function BottomTabBar({ active }: { active: Tab }) {
  return (
    <nav className={styles.bar}>
      {TABS.map((tab) => (
        <Link key={tab.key} to={tab.to} className={styles.item}>
          <span className={`${styles.dot} ${tab.key === active ? styles.dotActive : ''}`} />
          <span className={`${styles.label} ${tab.key === active ? styles.labelActive : ''}`}>{tab.label}</span>
        </Link>
      ))}
    </nav>
  );
}
