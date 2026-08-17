import { Avatar } from '../components/Avatar';
import { BottomTabBar } from '../components/BottomTabBar';
import { useAuth } from '../lib/auth/useAuth';
import { TAB_ROUTES, useSwipeEntryClass, useSwipeNavigation } from '../lib/nav/swipeNav';
import styles from './ProfileScreen.module.css';

export function ProfileScreen() {
  const { user } = useAuth();
  useSwipeNavigation(TAB_ROUTES);
  const swipeEntry = useSwipeEntryClass();

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
      </div>

      <BottomTabBar active="profile" />
    </div>
  );
}
