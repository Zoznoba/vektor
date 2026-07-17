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
