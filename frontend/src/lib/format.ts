export function timeAgo(isoDate: string | null): string {
  if (!isoDate) return '';
  const date = new Date(isoDate);
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return date.toLocaleDateString();
}

export function formatQuantity(amount: string | null, unit: string | null): string {
  return [amount, unit].filter(Boolean).join(' ');
}

/** Local-time YYYY-MM-DD key, so scans are bucketed by the user's calendar day. */
function dayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/**
 * Consecutive-day scan streak. Counts back from today (or yesterday, so the streak
 * stays "live" until you miss a full day) through days that have at least one scan.
 * Decrements by calendar day rather than 24h so it stays correct across DST.
 */
export function computeDayStreak(dates: (string | null)[], now: Date = new Date()): number {
  const days = new Set<string>();
  for (const iso of dates) {
    if (!iso) continue;
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) continue;
    days.add(dayKey(dt));
  }
  if (days.size === 0) return 0;

  const cursor = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (!days.has(dayKey(cursor))) {
    cursor.setDate(cursor.getDate() - 1);
    if (!days.has(dayKey(cursor))) return 0; // last scan was before yesterday
  }

  let streak = 0;
  while (days.has(dayKey(cursor))) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}
