import type { IconName } from '../components/icons/Icon';

export interface NavItem {
  key: string;
  label: string;
  icon: IconName;
}

/**
 * Состав пунктов сайдбара ученика зафиксирован — только эти 4,
 * без добавления новых до отдельного решения.
 * Соответствует Экрану 1 из ТЗ (п. 4.7).
 */
export const STUDENT_NAV_ITEMS: NavItem[] = [
  { key: 'home', label: 'Главная', icon: 'home' },
  { key: 'surveys', label: 'Анкеты', icon: 'file' },
  { key: 'results', label: 'Результаты', icon: 'chart' },
  { key: 'profile', label: 'Профиль', icon: 'user' },
];

/**
 * Сайдбар администратора — 6 пунктов из концепта (экран «Сводка»).
 * «360-тесты», «Импорт данных» и «Настройки» появятся после этапов 4–6
 * бэкенда — до тех пор пункты видимы, но ведут на заглушку.
 */
export const ADMIN_NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', label: 'Сводка', icon: 'dashboard' },
  { key: 'users', label: 'Пользователи', icon: 'users' },
  { key: 'classes', label: 'Классы', icon: 'school' },
  { key: 'tests', label: '360-тесты', icon: 'radar' },
  { key: 'import', label: 'Импорт данных', icon: 'upload' },
  { key: 'settings', label: 'Настройки', icon: 'settings' },
];

/** Маршруты разделов админки; ключи без маршрута — ещё не реализованы. */
export const ADMIN_ROUTES: Partial<Record<string, string>> = {
  dashboard: '/admin',
  users: '/admin/users',
  classes: '/admin/classes',
};
