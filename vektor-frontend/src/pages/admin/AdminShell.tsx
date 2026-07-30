import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../../components/layout/AppShell';
import { ADMIN_NAV_ITEMS, ADMIN_ROUTES } from '../../data/navigation';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABELS } from '../../types/auth';

interface AdminShellProps {
  activeNavKey: string;
  children: ReactNode;
}

/** Общий каркас страниц админки: сайдбар с навигацией по маршрутам + топбар. */
export function AdminShell({ activeNavKey, children }: AdminShellProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const handleNavigate = (key: string) => {
    const route = ADMIN_ROUTES[key];
    if (route) {
      navigate(route);
      return;
    }
    console.info(`Раздел «${key}» появится после реализации на бэкенде (этапы 4–6)`);
  };

  return (
    <AppShell
      navItems={ADMIN_NAV_ITEMS}
      activeNavKey={activeNavKey}
      onNavigate={handleNavigate}
      userFullName={user.full_name}
      userRoleLabel={ROLE_LABELS[user.role]}
      onLogout={logout}
    >
      {children}
    </AppShell>
  );
}
