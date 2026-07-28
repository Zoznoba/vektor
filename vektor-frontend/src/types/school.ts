/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/classes/schemas.py).
 */

import type { User } from './auth';

export interface SchoolClass {
  id: number;
  grade: number;
  section: string;
  homeroom_teacher: User | null;
  students: User[];
  teachers: User[];
}

/**
 * Человекочитаемое имя класса: секция-буква приклеивается («10А»),
 * секция-номер идёт через дефис («8-1»).
 */
export function classLabel(cls: Pick<SchoolClass, 'grade' | 'section'>): string {
  const section = cls.section.toUpperCase();
  return /^\d+$/.test(section) ? `${cls.grade}-${section}` : `${cls.grade}${section}`;
}
