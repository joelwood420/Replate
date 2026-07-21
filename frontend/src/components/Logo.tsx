import styles from './Logo.module.css';

type LogoVariant = 'splash' | 'signin';

interface VariantSpec {
  mark: number;
  glyph: number;
  wordmark: number;
  letterSpacing: string;
  gap: number;
  tagline: boolean;
}

const VARIANTS: Record<LogoVariant, VariantSpec> = {
  splash: { mark: 72, glyph: 30, wordmark: 30, letterSpacing: '0.22em', gap: 22, tagline: true },
  signin: { mark: 64, glyph: 26, wordmark: 26, letterSpacing: '0.14em', gap: 20, tagline: false },
};

export function Logo({ variant }: { variant: LogoVariant }) {
  const v = VARIANTS[variant];
  return (
    <div className={styles.wrap} style={{ gap: v.gap }}>
      <div className={styles.mark} style={{ width: v.mark, height: v.mark, fontSize: v.glyph }}>
        R
      </div>
      <div className={styles.textBlock}>
        <div className={styles.wordmark} style={{ fontSize: v.wordmark, letterSpacing: v.letterSpacing }}>
          REPLATE
        </div>
        {v.tagline && <div className={styles.tagline}>reverse-engineer any dish</div>}
      </div>
    </div>
  );
}
