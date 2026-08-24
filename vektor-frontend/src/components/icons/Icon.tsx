import type { SVGProps } from 'react';

/**
 * Тот же набор линейных иконок, что и в утверждённом UI-ките
 * (vektor-platform-design.html) — 24×24 viewBox, stroke 1.6px,
 * без внешних иконных библиотек и зависимостей.
 */
const PATHS: Record<string, string[]> = {
  home: ['M4 11.5 12 4l8 7.5', 'M6 10v9h12v-9', 'M10 19v-5h4v5'],
  file: [
    'M7 3h7l4 4v14H7z',
    'M14 3v4h4',
    'M9.5 9h3',
    'M9.5 12.5h6',
    'M9.5 16h6',
  ],
  chart: ['M4 20V11', 'M12 20V5', 'M20 20v-7', 'M3 20h18'],
  user: ['M12 8a3.4 3.4 0 1 0 0-6.8A3.4 3.4 0 0 0 12 8z', 'M5.5 19c1-3.6 4-5 6.5-5s5.5 1.4 6.5 5'],
  bell: ['M7 16v-5a5 5 0 0 1 10 0v5', 'M5 16h14', 'M10 19a2 2 0 0 0 4 0'],
  arrowLeft: ['M19 12H5', 'M11 18l-6-6 6-6'],
  arrowRight: ['M5 12h14', 'M13 6l6 6-6 6'],
  chevronDown: ['M6 9l6 6 6-6'],
  dashboard: ['M4 4h7v7H4z', 'M13 4h7v4h-7z', 'M13 11h7v9h-7z', 'M4 14h7v6H4z'],
  users: [
    'M9 8a3.2 3.2 0 1 0 0-6.4A3.2 3.2 0 0 0 9 8z',
    'M3 19c.9-3.4 3.6-4.8 6-4.8s5.1 1.4 6 4.8',
    'M15.5 2.2a3.2 3.2 0 0 1 0 5.6',
    'M17.5 14.6c1.8.6 3 1.9 3.5 4.4',
  ],
  school: ['M12 4 3 8.5 12 13l9-4.5z', 'M6 10.5V16c1.8 1.6 4 2.4 6 2.4s4.2-.8 6-2.4v-5.5', 'M21 8.5V14'],
  radar: [
    'M12 3l7.8 5.7-3 9.2H7.2l-3-9.2z',
    'M12 8.2l3.6 2.6-1.4 4.2h-4.4l-1.4-4.2z',
    'M12 3v5.2',
  ],
  upload: ['M12 16V4', 'M7 9l5-5 5 5', 'M4 20h16'],
  settings: [
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    'M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.5a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.5h4l.4-2.5a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z',
  ],
  plus: ['M12 5v14', 'M5 12h14'],
  search: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z', 'M20 20l-4-4'],
  x: ['M6 6l12 12', 'M18 6L6 18'],
  shieldLock: [
    'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z',
    'M9.5 12.5h5v4h-5z',
    'M10.3 12.5v-1.3a1.7 1.7 0 0 1 3.4 0v1.3',
  ],
  check: ['M5 13l4.5 4.5L19 8'],
  trash: ['M5 7h14', 'M9 7V5h6v2', 'M7 7l1 13h8l1-13'],
  archive: ['M4 4h16v4H4z', 'M6 8v12h12V8', 'M10 12h4'],
  arrowUp: ['M12 19V5', 'M6 11l6-6 6 6'],
  arrowDown: ['M12 5v14', 'M6 13l6 6 6-6'],
};

export type IconName = keyof typeof PATHS;

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'viewBox'> {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 20, ...rest }: IconProps) {
  const paths = PATHS[name];
  if (!paths) return null;

  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
