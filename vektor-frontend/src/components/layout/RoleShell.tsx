import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from './AppShell';
import {
  PARENT_NAV_ITEMS,
  PARENT_ROUTES,
  STUDENT_NAV_ITEMS,
  STUDENT_ROUTES,
  TEACHER_NAV_ITEMS,
  TEACHER_ROUTES,
  type NavItem,
} from '../../data/navigation';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABELS, type UserRole } from '../../types/auth';

interface RoleShellProps {
  /** Ключ активного пункта меню — из набора той роли, что залогинена. */
  activeNavKey: string;
  children: ReactNode;
}

/**
 * Набор пунктов и маршрутов по роли.
 *
 * Учитель — по прототипу: «Мои классы», «Анкеты», «Профиль ученика», без
 * «Главной» и без личных результатов. Родитель — «Результаты» (ребёнка) и
 * «Анкеты», без личного дашборда (он не субъект оценки в своей анкете).
 */
function navFor(role: UserRole): { items: NavItem[]; routes: Record<string, string> } {
  if (role === 'teacher') return { items: TEACHER_NAV_ITEMS, routes: TEACHER_ROUTES };
  if (role === 'parent') return { items: PARENT_NAV_ITEMS, routes: PARENT_ROUTES };
  return { items: STUDENT_NAV_ITEMS, routes: STUDENT_ROUTES };
}

/**
 * AppShell, знающий про роль: подставляет её меню и делает пункты кликабельными.
 *
 * Раньше каждая страница собирала AppShell сама и глушила навигацию в
 * console.info — отсюда и брались «мёртвые» пункты сайдбара.
 */
export function RoleShell({ activeNavKey, children }: RoleShellProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const { items, routes } = navFor(user.role);

  const handleNavigate = (key: string) => {
    if (key === activeNavKey) return;
    const route = routes[key];
    if (route) navigate(route);
  };

  return (
    <AppShell
      navItems={items}
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
