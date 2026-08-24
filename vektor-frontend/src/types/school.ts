/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/classes/schemas.py).
 */

import type { User } from './auth';

/**
 * Учитель в составе класса. subject и is_homeroom принадлежат ПАРЕ
 * «учитель + класс»: один и тот же человек ведёт литературу в 8-1 и русский
 * в 5-2, а классным руководителем может быть только в одном из них.
 */
export interface TeacherInClass {
  teacher: User;
  subject: string | null;
  is_homeroom: boolean;
}

export interface SchoolClass {
  id: number;
  grade: number;
  section: string;
  students: User[];
  teachers: TeacherInClass[];
}

/**
 * Классные руководители класса — их может быть несколько. Отдельным полем
 * бэкенд их не отдаёт намеренно: это те же строки teachers с флагом, и второй
 * список пришлось бы держать в согласии с первым.
 */
export function homeroomTeachers(cls: SchoolClass): TeacherInClass[] {
  return cls.teachers.filter((t) => t.is_homeroom);
}

/** Учителя-предметники: все, кроме классных руководителей. */
export function subjectTeachers(cls: SchoolClass): TeacherInClass[] {
  return cls.teachers.filter((t) => !t.is_homeroom);
}

/**
 * Человекочитаемое имя класса: секция-буква приклеивается («10А»),
 * секция-номер идёт через дефис («8-1»).
 */
export function classLabel(cls: Pick<SchoolClass, 'grade' | 'section'>): string {
  const section = cls.section.toUpperCase();
  return /^\d+$/.test(section) ? `${cls.grade}-${section}` : `${cls.grade}${section}`;
}
