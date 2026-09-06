/**
 * Разбор вставленного списка «ФИО<tab>email» — общий для мастера «Новый класс»
 * (AdminClassesPage) и для «Добавить пачкой» на «Пользователях».
 *
 * Жил внутри AdminClassesPage до тех пор, пока массовое заведение людей было
 * только там; после того как оно появилось и на самом экране пользователей,
 * копия разошлась бы с оригиналом на первой же правке валидации.
 */

/** Одна распарсенная строка ростера. error !== null → строку нельзя отправлять. */
export interface RosterRow {
  fullName: string;
  email: string;
  error: string | null;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Разделитель — таб (вставка из Excel) либо запятая/точка с запятой при
 * ручном вводе. Валидируем каждую строку: пустое ФИО, кривой/пустой email,
 * дубль внутри пачки, уже занятый в школе email — всё помечается, чтобы
 * админ починил ДО отправки (бэковый /users/bulk атомарен — либо всё, либо
 * ничего, так что частичной загрузки не будет).
 */
export function parseRoster(raw: string, existingEmails: Set<string>): RosterRow[] {
  const rows: RosterRow[] = [];
  const seen = new Set<string>();
  for (const rawLine of raw.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;
    const [namePart = '', emailPart = ''] = line.split(/[\t,;]/);
    const fullName = namePart.trim();
    const email = emailPart.trim();
    const emailKey = email.toLowerCase();

    let error: string | null = null;
    if (!fullName) error = 'пустое ФИО';
    else if (!email) error = 'нет email';
    else if (!EMAIL_RE.test(email)) error = 'некорректный email';
    else if (existingEmails.has(emailKey)) error = 'email уже занят в школе';
    else if (seen.has(emailKey)) error = 'дубль в списке';

    if (email && !error) seen.add(emailKey);
    rows.push({ fullName, email, error });
  }
  return rows;
}

/**
 * Превью распознанных строк. Одинаковое в обоих мастерах: и там, и там
 * задача одна — показать, что именно уедет на бэкенд, и подсветить, что
 * чинить.
 */
export function rosterErrorCount(rows: RosterRow[]): number {
  return rows.filter((r) => r.error).length;
}
