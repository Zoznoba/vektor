import type { ReactNode } from 'react';
import { Icon } from '../icons/Icon';
import './InfoBanner.css';

interface InfoBannerProps {
  children: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

export function InfoBanner({ children, actionLabel, onAction }: InfoBannerProps) {
  return (
    <div className="info-banner">
      <span className="info-banner__icon">
        <Icon name="bell" size={20} />
      </span>
      <span className="info-banner__text">{children}</span>
      {actionLabel && (
        <button type="button" className="info-banner__action" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
