/**
 * Период кампании — год + месяц числами (бэкенд отдаёт period_year /
 * period_month). Название месяца — это ОТОБРАЖЕНИЕ, поэтому живёт здесь, а
 * не в ответе API: бэкенд отдаёт доменные данные, а готовый текст под UI
 * собирает фронт (то же решение, что по badgeLabel анкет).
 */

/**
 * Именительный падеж, с заглавной — «Июнь 2026».
 *
 * Не toLocaleDateString('ru-RU', { month: 'long' }): в составе даты он даёт
 * родительный падеж («20 июня»), а нам нужен месяц сам по себе.
 */
export const MONTHS_RU = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
] as const;

/** «Июнь 2026». Месяц вне 1–12 (битые данные) деградирует до одного года. */
export function formatPeriod(year: number, month: number): string {
  const name = MONTHS_RU[month - 1];
  return name ? `${name} ${year}` : String(year);
}

/** Варианты для <select> месяца в форме кампании. */
export const MONTH_OPTIONS = MONTHS_RU.map((label, index) => ({ value: index + 1, label }));
