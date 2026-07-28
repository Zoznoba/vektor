import type { ReactNode } from 'react';
import { Topbar } from './Topbar';
import { Sidebar } from './Sidebar';
import type { NavItem } from '../../data/navigation';
import './AppShell.css';

interface AppShellProps {
  navItems: NavItem[];
  activeNavKey: string;
  onNavigate?: (key: string) => void;
  userFullName: string;
  userRoleLabel: string;
  onLogout?: () => void;
  children: ReactNode;
}

export function AppShell({
  navItems,
  activeNavKey,
  onNavigate,
  userFullName,
  userRoleLabel,
  onLogout,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <Topbar userFullName={userFullName} userRoleLabel={userRoleLabel} onLogout={onLogout} />
      <div className="app-body">
        <Sidebar items={navItems} activeKey={activeNavKey} onNavigate={onNavigate} />
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
