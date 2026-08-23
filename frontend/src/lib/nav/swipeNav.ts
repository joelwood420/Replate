import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import styles from './swipe.module.css';

// The bottom-tab destinations, in tab order. Swiping left goes to the next tab,
// right to the previous. A single frozen array keeps the hook's effect deps stable.
export const TAB_ROUTES = ['/home', '/cookbook', '/profile'] as const;

type SwipeDir = 'forward' | 'back';

const H_THRESHOLD = 60; // min horizontal travel (px) to count as a swipe
const V_LIMIT = 45; // max vertical drift (px) before we treat it as a scroll, not a swipe
const EDGE_GUARD = 24; // px from a screen edge to ignore, so iOS back/forward edge-swipes don't clash

/**
 * Horizontal swipe between the given ordered routes. Call from a tab screen: a
 * pointer drag past the threshold navigates to the adjacent tab and records the
 * direction in history state, so the incoming screen can animate accordingly.
 * Listens on the window via Pointer Events, so it covers touch drags on device
 * and mouse drags in a desktop browser.
 *
 * The end of the gesture is evaluated from the last tracked position on BOTH
 * `pointerup` and `pointercancel`. On touch, a browser can decide mid-drag that a
 * horizontal move is a scroll and fire `pointercancel` instead of `pointerup`
 * (`#root` sets `touch-action: pan-y` to discourage this, but not every engine
 * honours it the same way), so relying on `pointerup` alone silently drops swipes
 * on mobile. The threshold checks make `pointercancel` safe: a real vertical
 * scroll has too much vertical drift to pass.
 */
export function useSwipeNavigation(routes: readonly string[]) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    const index = routes.indexOf(pathname);
    if (index === -1) return undefined;

    let startX = 0;
    let startY = 0;
    let lastX = 0;
    let lastY = 0;
    let active = false;

    function onDown(e: PointerEvent) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      // Let horizontally-scrollable regions (e.g. the cookbook filter chips) keep their gesture.
      if ((e.target as HTMLElement | null)?.closest('[data-noswipe]')) {
        active = false;
        return;
      }
      // Ignore gestures starting at the very edge: iOS reserves those for its own
      // back/forward navigation, so we'd fight the system gesture and usually lose.
      if (e.clientX <= EDGE_GUARD || e.clientX >= window.innerWidth - EDGE_GUARD) {
        active = false;
        return;
      }
      startX = lastX = e.clientX;
      startY = lastY = e.clientY;
      active = true;
    }

    function onMove(e: PointerEvent) {
      if (!active) return;
      lastX = e.clientX;
      lastY = e.clientY;
    }

    function onEnd() {
      if (!active) return;
      active = false;
      const dx = lastX - startX;
      const dy = lastY - startY;
      // Ignore short drags and anything more vertical than horizontal (a scroll).
      if (Math.abs(dx) < H_THRESHOLD || Math.abs(dy) > V_LIMIT) return;
      const target = dx < 0 ? index + 1 : index - 1;
      if (target < 0 || target >= routes.length) return;
      const dir: SwipeDir = dx < 0 ? 'forward' : 'back';
      navigate(routes[target], { state: { dir } });
    }

    window.addEventListener('pointerdown', onDown, { passive: true });
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerup', onEnd, { passive: true });
    window.addEventListener('pointercancel', onEnd, { passive: true });
    return () => {
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
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
