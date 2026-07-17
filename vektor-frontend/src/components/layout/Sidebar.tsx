import { Icon } from '../icons/Icon';
import type { NavItem } from '../../data/navigation';
import './Sidebar.css';

interface SidebarProps {
  items: NavItem[];
  activeKey: string;
  /** Пока есть только страница «Главная» — остальные пункты неактивны визуально, но не скрыты */
  onNavigate?: (key: string) => void;
}

export function Sidebar({ items, activeKey, onNavigate }: SidebarProps) {
  return (
    <nav className="app-sidebar" aria-label="Основная навигация">
      {items.map((item) => {
        const isActive = item.key === activeKey;
        return (
          <button
            key={item.key}
            type="button"
            className={`nav-item ${isActive ? 'nav-item--active' : ''}`.trim()}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => onNavigate?.(item.key)}
          >
            <span className="nav-item__icon">
              <Icon name={item.icon} size={20} />
            </span>
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
