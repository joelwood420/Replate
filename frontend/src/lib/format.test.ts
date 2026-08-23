import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { computeDayStreak, formatQuantity, timeAgo } from './format';

describe('timeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Fixed "now" so the relative buckets are deterministic.
    vi.setSystemTime(new Date('2026-08-22T12:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns empty string for null', () => {
    expect(timeAgo(null)).toBe('');
  });

  it('returns "just now" under a minute', () => {
    expect(timeAgo('2026-08-22T11:59:30.000Z')).toBe('just now');
  });

  it('formats minutes', () => {
    expect(timeAgo('2026-08-22T11:45:00.000Z')).toBe('15m ago');
  });

  it('formats hours', () => {
    expect(timeAgo('2026-08-22T09:00:00.000Z')).toBe('3h ago');
  });

  it('says "Yesterday" at exactly one day', () => {
    expect(timeAgo('2026-08-21T12:00:00.000Z')).toBe('Yesterday');
  });

  it('formats days under a week', () => {
    expect(timeAgo('2026-08-19T12:00:00.000Z')).toBe('3 days ago');
  });

  it('formats weeks under five', () => {
    expect(timeAgo('2026-08-01T12:00:00.000Z')).toBe('3w ago');
  });

  it('falls back to a locale date past five weeks', () => {
    // Older than 5 weeks: exact copy is locale-dependent, so just assert it is a
    // concrete date string, not one of the relative buckets.
    const result = timeAgo('2026-01-01T12:00:00.000Z');
    expect(result).not.toBe('');
    expect(result).not.toMatch(/ago|Yesterday|just now/);
  });
});

describe('computeDayStreak', () => {
  // Local noon on 2026-08-22, and scan timestamps without a 'Z' so they parse as
  // local time too — keeps the calendar-day bucketing deterministic across zones.
  const now = new Date(2026, 7, 22, 12, 0, 0);

  it('returns 0 for no scans', () => {
    expect(computeDayStreak([], now)).toBe(0);
  });

  it('ignores null and unparseable dates', () => {
    expect(computeDayStreak([null, 'not-a-date'], now)).toBe(0);
  });

  it('counts a single scan today as a streak of 1', () => {
    expect(computeDayStreak(['2026-08-22T09:00:00'], now)).toBe(1);
  });

  it('counts consecutive days ending today', () => {
    expect(
      computeDayStreak(['2026-08-22T09:00:00', '2026-08-21T20:00:00', '2026-08-20T08:00:00'], now),
    ).toBe(3);
  });

  it('collapses multiple scans on the same day', () => {
    expect(
      computeDayStreak(['2026-08-22T09:00:00', '2026-08-22T21:00:00', '2026-08-21T10:00:00'], now),
    ).toBe(2);
  });

  it('stays live when the last scan was yesterday', () => {
    expect(computeDayStreak(['2026-08-21T09:00:00', '2026-08-20T09:00:00'], now)).toBe(2);
  });

  it('is 0 when the last scan was before yesterday', () => {
    expect(computeDayStreak(['2026-08-20T09:00:00'], now)).toBe(0);
  });

  it('stops at the first gap', () => {
    expect(
      computeDayStreak(['2026-08-22T09:00:00', '2026-08-20T09:00:00', '2026-08-19T09:00:00'], now),
    ).toBe(1);
  });
});

describe('formatQuantity', () => {
  it('joins amount and unit', () => {
    expect(formatQuantity('2', 'cups')).toBe('2 cups');
  });

  it('drops a missing unit', () => {
    expect(formatQuantity('2', null)).toBe('2');
  });

  it('drops a missing amount', () => {
    expect(formatQuantity(null, 'pinch')).toBe('pinch');
  });

  it('returns empty when both are missing', () => {
    expect(formatQuantity(null, null)).toBe('');
  });
});
