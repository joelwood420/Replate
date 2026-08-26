import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Avatar } from '../components/Avatar';
import { BottomTabBar } from '../components/BottomTabBar';
import { ScanCard } from '../components/ScanCard';
import { useAuth } from '../lib/auth/useAuth';
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

      <BottomTabBar active="home" />
    </div>
  );
}
