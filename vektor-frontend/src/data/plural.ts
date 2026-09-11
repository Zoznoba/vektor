/**
 * Русская форма слова по числу: «1 ученик», «2 ученика», «5 учеников».
 *
 * Живёт во фронте, а не в ответе API, по тому же решению, что названия
 * месяцев (data/period.ts): бэкенд отдаёт доменные данные, готовый текст под
 * UI собирает фронт.
 *
 * Intl.PluralRules('ru') различает те же три формы, но требует свой словарь
 * для каждой категории — на три слова это больше кода, чем сам расчёт.
 */
export function plural(count: number, forms: [string, string, string]): string {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (n1 > 1 && n1 < 5) return forms[1];
  if (n1 === 1) return forms[0];
  return forms[2];
}

/** «136 учеников» — число вместе с согласованным словом. */
export function withPlural(count: number, forms: [string, string, string]): string {
  return `${count} ${plural(count, forms)}`;
}
