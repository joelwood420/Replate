import type { ComponentType } from 'react';
import { Link } from 'react-router-dom';
import { IconCookbook, IconHome, IconProfile } from './icons';
import styles from './BottomTabBar.module.css';

type Tab = 'home' | 'cookbook' | 'profile';

const TABS: { key: Tab; label: string; to: string; Icon: ComponentType<{ size?: number }> }[] = [
  { key: 'home', label: 'Home', to: '/home', Icon: IconHome },
  { key: 'cookbook', label: 'Cookbook', to: '/cookbook', Icon: IconCookbook },
  { key: 'profile', label: 'Profile', to: '/profile', Icon: IconProfile },
];

export function BottomTabBar({ active }: { active: Tab }) {
  return (
    <nav className={styles.bar}>
      {TABS.map(({ key, label, to, Icon }) => {
        const isActive = key === active;
        return (
          <Link
            key={key}
            to={to}
            className={`${styles.item} ${isActive ? styles.itemActive : ''}`}
            aria-current={isActive ? 'page' : undefined}
          >
            <Icon size={22} />
            <span className={styles.label}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
