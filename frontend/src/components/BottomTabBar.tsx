import { Link } from 'react-router-dom';
import styles from './BottomTabBar.module.css';

type Tab = 'home' | 'cookbook' | 'profile';

const TABS: { key: Tab; label: string; to: string }[] = [
  { key: 'home', label: 'Home', to: '/home' },
  { key: 'cookbook', label: 'Cookbook', to: '/cookbook' },
  { key: 'profile', label: 'Profile', to: '/profile' },
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
