/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/cases/schemas.py).
 *
 * Кейс — профильная группа (кружок): ученики из РАЗНЫХ классов под
 * руководством 2–3 учителей. Ключевое отличие от класса — членство ровно
 * одно и у ученика, и у учителя, поэтому у связи нет атрибутов (ср.
 * TeacherInClass с subject/is_homeroom): кейс сам по себе и есть профильная
 * деятельность.
 */

import type { User } from './auth';

export interface Case {
  id: number;
  name: string;
  description: string | null;
  /**
   * Два отдельных списка, а не общий members с ролью внутри: на экране это
   * две разные вкладки, и фильтровать по роли в каждом месте пришлось бы
   * фронту. Бэкенд разделяет их на уровне модели, здесь это бесплатно.
   */
  students: User[];
  teachers: User[];
}

/** Все участники кейса одним списком — для проверок «этот человек уже занят». */
export function caseMembers(kase: Case): User[] {
  return [...kase.students, ...kase.teachers];
}
