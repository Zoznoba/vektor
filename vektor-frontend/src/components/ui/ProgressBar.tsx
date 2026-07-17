import './ProgressBar.css';

interface ProgressBarProps {
  /** Заполнение в процентах, 0–100 */
  value: number;
  variant?: 'lime' | 'blue';
  className?: string;
}

export function ProgressBar({ value, variant = 'lime', className = '' }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      className={`progress ${variant === 'blue' ? 'progress--blue' : ''} ${className}`.trim()}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div style={{ width: `${clamped}%` }} />
    </div>
  );
}
