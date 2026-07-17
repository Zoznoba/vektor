import type { ReactNode } from 'react';
import './Badge.css';

type BadgeVariant = 'lime' | 'blue' | 'amber' | 'red';

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = 'lime', children, className = '' }: BadgeProps) {
  return <span className={`badge badge-${variant} ${className}`.trim()}>{children}</span>;
}
