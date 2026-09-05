import type { IconName } from '../components/icons/Icon';

export interface NavItem {
  key: string;
  label: string;
  icon: IconName;
}

/**
 * Сайдбар ученика. В ТЗ (п. 4.7, Экран 1) пунктов было четыре, но
 * «Результаты» и «Профиль» так и остались без своих экранов: результаты
 * ученика живут прямо на «Главной», отдельного профиля нет вовсе. Пункт,
 * который ничего не делает по клику, читается как поломка, поэтому их
 * убрали. Вернуть — значит вернуть строку сюда и маршрут в STUDENT_ROUTES.
 */
export const STUDENT_NAV_ITEMS: NavItem[] = [
  { key: 'home', label: 'Главная', icon: 'home' },
  { key: 'surveys', label: 'Анкеты', icon: 'file' },
];

/**
 * Сайдбар учителя — три пункта из прототипа (ref/Платформа Вектор.dc.html,
 * роль teacher). «Главной» и «Профиля» у учителя нет намеренно: стартовый
 * экран — «Мои классы», а личных результатов у учителя не бывает (он не
 * субъект оценки, а оценивающий).
 */
export const TEACHER_NAV_ITEMS: NavItem[] = [
  { key: 'classes', label: 'Мои классы', icon: 'school' },
  // «Мои кейсы» — профильная группа учителя (Этап 8). Пункт показываем всем
  // учителям, а не только тем, у кого кейс есть: сайдбар статичен по роли, а
  // экран сам объясняет пустое состояние («вы не привязаны ни к одному кейсу»).
  { key: 'cases', label: 'Мои кейсы', icon: 'briefcase' },
  { key: 'surveys', label: 'Анкеты', icon: 'file' },
  { key: 'students', label: 'Профиль ученика', icon: 'radar' },
];

/**
 * Сайдбар родителя — по прототипу (роль parentchild): «Результаты» —
 * стартовый экран (данные ребёнка, с переключателем при 2+ детях), «Анкеты» —
 * родитель тоже оценивает своего ребёнка в рамках кампании 360°.
 */
export const PARENT_NAV_ITEMS: NavItem[] = [
  { key: 'results', label: 'Результаты', icon: 'radar' },
  { key: 'surveys', label: 'Анкеты', icon: 'file' },
];

/** Маршруты разделов ученика — по одному на каждый пункт сайдбара. */
export const STUDENT_ROUTES: Record<string, string> = {
  home: '/',
  surveys: '/surveys',
};

/** Маршруты разделов учителя. */
export const TEACHER_ROUTES: Record<string, string> = {
  classes: '/teacher/classes',
  cases: '/teacher/cases',
  surveys: '/surveys',
  students: '/teacher/students',
};

/** Маршруты разделов родителя. */
export const PARENT_ROUTES: Record<string, string> = {
  results: '/parent/results',
  surveys: '/surveys',
};

/**
 * Сайдбар администратора. «Импорт данных» и «Настройки» из концепта убраны:
 * своих экранов у них нет (импорт живёт дампом seed/demo_data.sql, см.
 * CLAUDE.md, Этап 6), а пункт, который ничего не делает по клику, читается
 * как поломка — та же причина, по которой у ученика убраны «Результаты» и
 * «Профиль». Теперь у КАЖДОГО пункта каждой роли есть свой маршрут.
 */
export const ADMIN_NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', label: 'Сводка', icon: 'dashboard' },
  { key: 'users', label: 'Пользователи', icon: 'users' },
  { key: 'classes', label: 'Классы', icon: 'school' },
  { key: 'cases', label: 'Кейсы', icon: 'briefcase' },
  { key: 'tests', label: 'Диагностика', icon: 'radar' },
  { key: 'results', label: 'Результаты', icon: 'chart' },
];

/** Маршруты разделов админки. */
export const ADMIN_ROUTES: Record<string, string> = {
  dashboard: '/admin',
  users: '/admin/users',
  classes: '/admin/classes',
  cases: '/admin/cases',
  tests: '/admin/campaigns',
  results: '/admin/results',
};
