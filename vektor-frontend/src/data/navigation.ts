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
