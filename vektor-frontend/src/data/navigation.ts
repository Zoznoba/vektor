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
 * Сайдбар учителя — три пункта из прототипа (ref/Платформа Вектор.dc.html,
 * роль teacher). «Главной» и «Профиля» у учителя нет намеренно: стартовый
 * экран — «Мои классы», а личных результатов у учителя не бывает (он не
 * субъект оценки, а оценивающий).
 */
export const TEACHER_NAV_ITEMS: NavItem[] = [
  { key: 'classes', label: 'Мои классы', icon: 'school' },
  { key: 'surveys', label: 'Анкеты', icon: 'file' },
  { key: 'students', label: 'Профиль ученика', icon: 'radar' },
];

/**
 * Маршруты разделов ученика. Ключи без маршрута («Результаты», «Профиль») ещё
 * не реализованы: пункт остаётся видимым, но клик ничего не делает — это
 * честнее, чем увести на несуществующую страницу и вернуть на главную.
 * Результаты ученика пока живут на самой «Главной».
 */
export const STUDENT_ROUTES: Record<string, string> = {
  home: '/',
  surveys: '/surveys',
};

/** Маршруты разделов учителя. */
export const TEACHER_ROUTES: Record<string, string> = {
  classes: '/teacher/classes',
  surveys: '/surveys',
  students: '/teacher/students',
};

/**
 * Сайдбар администратора — 6 пунктов из концепта (экран «Сводка»).
 * «Импорт данных» и «Настройки» появятся после Этапа 6 бэкенда — до тех
 * пор пункты видимы, но ведут на заглушку.
 */
export const ADMIN_NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', label: 'Сводка', icon: 'dashboard' },
  { key: 'users', label: 'Пользователи', icon: 'users' },
  { key: 'classes', label: 'Классы', icon: 'school' },
  { key: 'tests', label: 'Диагностика', icon: 'radar' },
  { key: 'import', label: 'Импорт данных', icon: 'upload' },
  { key: 'settings', label: 'Настройки', icon: 'settings' },
];

/** Маршруты разделов админки; ключи без маршрута — ещё не реализованы. */
export const ADMIN_ROUTES: Partial<Record<string, string>> = {
  dashboard: '/admin',
  users: '/admin/users',
  classes: '/admin/classes',
  tests: '/admin/campaigns',
};
