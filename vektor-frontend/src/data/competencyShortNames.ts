/**
 * Короткие подписи критериев — под оси радара.
 *
 * Полные названия методики («Умение управлять обучением и применять знания в
 * новых ситуациях») на оси не помещаются. В прототипе для этого есть отдельное
 * поле `short` у критерия; в нашей БД его нет, а заводить колонку ради подписи
 * не стали — это чистое представление. Ключ — стабильный `code`, а не имя:
 * формулировки различаются между редакциями анкеты, коды нет.
 */
const SHORT_NAMES: Record<string, string> = {
  self_awareness: 'Самосознание',
  emotional_intelligence: 'Эмоции',
  strengths_weaknesses: 'Сильные стороны',
  goal_setting: 'Цели',
  goal_planning: 'Планирование',
  learning_autonomy: 'Самостоятельность',
  learning_transfer: 'Перенос знаний',
  career_self_awareness: 'Проф. самосознание',
  proactive_stance: 'Проактивность',
  responsibility: 'Ответственность',
  career_exploration: 'Профпробы',
};

/** Незнакомый код (новый критерий) — обрезаем полное имя, а не падаем. */
export function shortCompetencyName(code: string, fallbackName: string): string {
  return SHORT_NAMES[code] ?? (fallbackName.length > 18 ? `${fallbackName.slice(0, 17)}…` : fallbackName);
}
