import { useEffect, useState } from 'react';
import styles from './ProcessingOrb.module.css';

const PHRASES = [
  'Deconstructing the sauce…',
  'Tasting notes: butter, thyme, patience…',
  'Cross-checking the menu…',
  'Reducing to the essentials…',
  'Searching for umami…',
  'Consulting the sous chef…',
  'Measuring by eye…',
  'Letting it simmer…',
  'Reverse-engineering flavor…',
  'Plating your recipe…',
];

const PHRASE_INTERVAL_MS = 2400;

// Cycles on a timer independent of real pipeline progress, per the design note that either
// approach is fine visually - GET /api/jobs/{jobId} only exposes Queued/Processing/
// Completed/Failed, not finer-grained pipeline stages.
export function ProcessingOrb() {
  const [phraseIndex, setPhraseIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setPhraseIndex((i) => (i + 1) % PHRASES.length);
    }, PHRASE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className={styles.wrap}>
      <div className={styles.orb}>
        <div className={styles.track} />
        <div className={styles.spinner}>
          <div className={styles.arc} />
          <div className={styles.dot} />
        </div>
        <div className={styles.glyph}>R</div>
      </div>
      <div className={styles.phraseBox}>
        <div key={phraseIndex} className={styles.phrase}>
          {PHRASES[phraseIndex]}
        </div>
      </div>
    </div>
  );
}
