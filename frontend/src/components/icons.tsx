/**
 * The app's authored line-icon set. One consistent stroke (1.5) and weight, drawn on a
 * 24-grid, coloured via `currentColor` so a parent sets gold/cream/muted. This replaces the
 * OS emoji that used to stand in for icons: emoji render differently per platform and don't
 * belong to the candlelit system.
 */
interface IconProps {
  size?: number;
  className?: string;
}

function svgProps(size: number, className?: string, strokeWidth = 1.5) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    className,
  };
}

export function IconClose({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function IconCamera({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <rect x="2" y="6" width="20" height="14" rx="3" />
      <path d="M8 6 7.4 3.4A1.2 1.2 0 0 1 8.6 2.2h6.8a1.2 1.2 0 0 1 1.2 1.2L17 6" />
      <circle cx="12" cy="13" r="3.5" />
    </svg>
  );
}

export function IconFlipCamera({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M4 9a8 8 0 0 1 13.5-3.2L20 8" />
      <path d="M20 8V4M20 8h-4" />
      <path d="M20 15a8 8 0 0 1-13.5 3.2L4 16" />
      <path d="M4 16v4M4 16h4" />
    </svg>
  );
}

export function IconLibrary({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <rect x="3" y="3" width="14" height="14" rx="2.5" />
      <circle cx="8" cy="8" r="1.4" />
      <path d="M3 13l3.5-3L11 14" />
      <path d="M20 8v11a2 2 0 0 1-2 2H7" opacity="0.5" />
    </svg>
  );
}

export function IconHome({ size = 22, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M4 11l8-6 8 6" />
      <path d="M6 10v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9" />
      <path d="M10 20v-5h4v5" />
    </svg>
  );
}

export function IconCookbook({ size = 22, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M5.5 3H19a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H5.5A1.5 1.5 0 0 1 4 18.5v-14A1.5 1.5 0 0 1 5.5 3Z" />
      <path d="M8 3v18" />
      <path d="M12 8h4.5M12 11h4.5" />
    </svg>
  );
}

export function IconProfile({ size = 22, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </svg>
  );
}

// Small action marks, a touch heavier (stroke 2) so they stay crisp at 11-16px.
export function IconBack({ size = 16, className }: IconProps) {
  return (
    <svg {...svgProps(size, className, 2)}>
      <path d="M19 12H6" />
      <path d="M12 5l-7 7 7 7" />
    </svg>
  );
}

export function IconPlus({ size = 14, className }: IconProps) {
  return (
    <svg {...svgProps(size, className, 2)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconCheck({ size = 12, className }: IconProps) {
  return (
    <svg {...svgProps(size, className, 2.4)}>
      <path d="M4.5 12.5l4.5 4.5L19.5 6.5" />
    </svg>
  );
}

export function IconEdit({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M4 20h4l10-10a2 2 0 0 0-2.8-2.8L5.2 17.2 4 20Z" />
      <path d="M14 6.2 17.8 10" />
    </svg>
  );
}

export function IconBell({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </svg>
  );
}

export function IconHelp({ size = 18, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 0 1 4.5 1.5c0 1.8-2.5 2-2.5 3.5" />
      <path d="M12 17.5h.01" />
    </svg>
  );
}

export function IconChevron({ size = 16, className }: IconProps) {
  return (
    <svg {...svgProps(size, className, 2)}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

export function IconTrash({ size = 14, className }: IconProps) {
  return (
    <svg {...svgProps(size, className, 2)}>
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M6 6l1 14a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-14" />
    </svg>
  );
}

export function IconHeart({ size = 20, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M12 20.5s-7-4.4-9.2-8.8C1.3 8.4 2.7 5.5 5.9 5.5c2 0 3.4 1.2 4.1 2.4l2-.1c.7-1.2 2.1-2.3 4-2.3 3.2 0 4.6 2.9 3.2 6.2C17 16.1 12 20.5 12 20.5Z" />
    </svg>
  );
}

export function IconFlame({ size = 20, className }: IconProps) {
  return (
    <svg {...svgProps(size, className)}>
      <path d="M12 3c1.5 3 4.5 4.2 4.5 8a4.5 4.5 0 0 1-9 0c0-1.2.5-2.2 1.2-3 .2 1 .9 1.7 1.6 1.7.9 0 1.2-.9.9-2.1C10.6 5.6 11 4.1 12 3Z" />
    </svg>
  );
}
