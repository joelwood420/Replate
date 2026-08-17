import { useNavigate } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { BottomTabBar } from '../components/BottomTabBar';
import { useAuth } from '../lib/auth/useAuth';
import { TAB_ROUTES, useSwipeEntryClass, useSwipeNavigation } from '../lib/nav/swipeNav';
import styles from './ProfileScreen.module.css';

export function ProfileScreen() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  useSwipeNavigation(TAB_ROUTES);
  const swipeEntry = useSwipeEntryClass();

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
