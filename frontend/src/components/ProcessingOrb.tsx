import { useEffect, useState } from 'react';
import styles from './ProcessingOrb.module.css';

/**
 * The two pipeline stages share the orb's DNA but not its weight. Stage 1 (identify) is
 * the quick at-the-table glance; stage 2 (generate) is the slow, expensive reduction that
 * rebuilds every component. They get different phrase pools so a phase never narrates the
 * wrong work, a different tempo, and a reassuring time hint on the long one.
 */
export type OrbStage = 'identify' | 'generate';

// Fast, "what is this / does it match the menu" phrases. Nothing here talks about writing
// a recipe — that work hasn't started yet at stage 1.
const IDENTIFY_PHRASES = [
  'Reading the plate…',
  'Finding the restaurant…',
  'Cross-checking the real menu…',
  'Naming what’s on the plate…',
  'Measuring by eye…',
  'Matching against the menu…',
];

// Slow, deliberate "building the method" phrases for the expensive stage-2 call.
const GENERATE_PHRASES = [
  'Deconstructing the sauce…',
  'Reverse-engineering every component…',
  'Tasting notes: butter, thyme, patience…',
  'Reducing to the essentials…',
  'Consulting the sous chef…',
  'Letting it simmer…',
  'Writing the method…',
  'Plating your recipe…',
];

const STAGE_CONFIG: Record<OrbStage, { phrases: string[]; intervalMs: number; subline?: string }> = {
  identify: { phrases: IDENTIFY_PHRASES, intervalMs: 2400 },
  generate: {
    phrases: GENERATE_PHRASES,
    intervalMs: 3200,
    subline: 'This one takes a little longer — we’re rebuilding every component.',
  },
};

// Cycles on a timer independent of real pipeline progress: GET /api/jobs/{jobId} only
// exposes coarse status (Processing / Generating), not finer-grained pipeline stages, so
// the phrases set an honest mood rather than a fake progress bar.
export function ProcessingOrb({ stage = 'identify' }: { stage?: OrbStage }) {
  const { phrases, intervalMs, subline } = STAGE_CONFIG[stage];
  const [phraseIndex, setPhraseIndex] = useState(0);

  // Reset when the stage changes so a stale index can't point past a shorter phrase list.
  useEffect(() => {
    setPhraseIndex(0);
    const timer = setInterval(() => {
      setPhraseIndex((i) => (i + 1) % phrases.length);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [stage, phrases.length, intervalMs]);

  const isGenerate = stage === 'generate';

  return (
    <div className={styles.wrap}>
      <div className={`${styles.orb} ${isGenerate ? styles.orbGenerate : ''}`}>
        <div className={styles.track} />
        <div className={styles.spinner}>
          <div className={styles.arc} />
          <div className={styles.dot} />
        </div>
        <div className={styles.glyph}>R</div>
      </div>
      <div className={styles.phraseBox} role="status" aria-live="polite">
        <div
          key={`${stage}-${phraseIndex}`}
          className={`${styles.phrase} ${isGenerate ? styles.phraseSlow : ''}`}
        >
          {phrases[phraseIndex]}
        </div>
      </div>
      {subline && <p className={styles.subline}>{subline}</p>}
    </div>
  );
}
