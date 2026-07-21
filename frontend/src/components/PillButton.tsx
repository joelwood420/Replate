import type { ButtonHTMLAttributes } from 'react';
import styles from './PillButton.module.css';

interface PillButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'cta' | 'footer';
}

export function PillButton({ variant = 'cta', className, ...rest }: PillButtonProps) {
  const classes = [styles.button, styles[variant], className].filter(Boolean).join(' ');
  return <button className={classes} {...rest} />;
}
