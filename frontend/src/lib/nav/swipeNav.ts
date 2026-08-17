import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import styles from './swipe.module.css';

// The bottom-tab destinations, in tab order. Swiping left goes to the next tab,
// right to the previous. A single frozen array keeps the hook's effect deps stable.
export const TAB_ROUTES = ['/home', '/cookbook', '/profile'] as const;

type SwipeDir = 'forward' | 'back';

const H_THRESHOLD = 60; // min horizontal travel (px) to count as a swipe
const V_LIMIT = 45; // max vertical drift (px) before we treat it as a scroll, not a swipe

/**
 * Horizontal swipe between the given ordered routes. Call from a tab screen: a
 * pointer drag past the threshold navigates to the adjacent tab and records the
 * direction in history state, so the incoming screen can animate accordingly.
 * Listens on the window via Pointer Events, so it covers touch drags on device
 * and mouse drags in a desktop browser.
 */
export function useSwipeNavigation(routes: readonly string[]) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    const index = routes.indexOf(pathname);
    if (index === -1) return undefined;

    let startX = 0;
    let startY = 0;
    let active = false;

    function onDown(e: PointerEvent) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      // Let horizontally-scrollable regions (e.g. the cookbook filter chips) keep their gesture.
      if ((e.target as HTMLElement | null)?.closest('[data-noswipe]')) {
        active = false;
        return;
      }
      startX = e.clientX;
      startY = e.clientY;
      active = true;
    }

    function onUp(e: PointerEvent) {
      if (!active) return;
      active = false;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      // Ignore short drags and anything more vertical than horizontal (a scroll).
      if (Math.abs(dx) < H_THRESHOLD || Math.abs(dy) > V_LIMIT) return;
      const target = dx < 0 ? index + 1 : index - 1;
      if (target < 0 || target >= routes.length) return;
      const dir: SwipeDir = dx < 0 ? 'forward' : 'back';
      navigate(routes[target], { state: { dir } });
    }

    window.addEventListener('pointerdown', onDown, { passive: true });
    window.addEventListener('pointerup', onUp, { passive: true });
    return () => {
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointerup', onUp);
    };
  }, [pathname, navigate, routes]);
}

/**
 * Class name for a tab screen's entry animation, based on the swipe direction
 * recorded in history state. Empty when the screen wasn't reached by a swipe
 * (a tab tap or a fresh load), so those transitions stay instant.
 */
export function useSwipeEntryClass(): string {
  const { state } = useLocation();
  const dir = (state as { dir?: SwipeDir } | null)?.dir;
  if (dir === 'forward') return styles.enterForward;
  if (dir === 'back') return styles.enterBack;
  return '';
}
