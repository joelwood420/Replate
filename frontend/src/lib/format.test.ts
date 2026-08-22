import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { formatQuantity, timeAgo } from './format';

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
