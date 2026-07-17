import type { ReactNode } from 'react';
import './Panel.css';

interface PanelProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, children, className = '' }: PanelProps) {
  return (
    <div className={`panel ${className}`.trim()}>
      {title && <div className="panel-title">{title}</div>}
      {children}
    </div>
  );
}
