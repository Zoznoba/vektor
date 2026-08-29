import { apiRequest } from './client';
import type { SchoolClass } from '../types/school';

export function fetchClasses(): Promise<SchoolClass[]> {
  return apiRequest<SchoolClass[]>('/classes');
}

export function createClass(grade: number, section: string): Promise<SchoolClass> {
  return apiRequest<SchoolClass>('/classes', { method: 'POST', body: { grade, section } });
}

export function assignStudents(classId: number, studentIds: number[]): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/students`, {
    method: 'POST',
    body: { student_ids: studentIds },
  });
}

/** subject/is_homeroom — общие на всю пачку; точечно правит updateTeacherInClass. */
export function assignTeachers(
  classId: number,
  teacherIds: number[],
  options: { subject?: string | null; isHomeroom?: boolean } = {},
): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/teachers`, {
    method: 'POST',
    body: {
      teacher_ids: teacherIds,
      subject: options.subject ?? null,
      is_homeroom: options.isHomeroom ?? false,
    },
  });
}

/**
 * Правка связи «учитель ↔ класс». Отправляем только то, что меняем: бэкенд
 * различает «ключа нет» (не трогать) и `subject: null` (стереть предмет),
 * поэтому собирать тело со всеми полями подряд нельзя.
 */
export function updateTeacherInClass(
  classId: number,
  teacherId: number,
  changes: { subject?: string | null; is_homeroom?: boolean },
): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/teachers/${teacherId}`, {
    method: 'PATCH',
    body: changes,
  });
}

export function removeTeacherFromClass(
  classId: number,
  teacherId: number,
): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/teachers/${teacherId}`, {
    method: 'DELETE',
  });
}

export function removeStudentFromClass(
  classId: number,
  studentId: number,
): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/students/${studentId}`, {
    method: 'DELETE',
  });
}

/**
 * Bulk-открепление под массовое выделение в таблице состава. Атомарно: если
 * хоть кого-то из списка в классе нет, не открепляется никто. POST, а не
 * DELETE, потому что тело у DELETE режут прокси.
 */
export function removeTeachersFromClass(
  classId: number,
  teacherIds: number[],
): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/teachers/detach`, {
    method: 'POST',
    body: { teacher_ids: teacherIds },
  });
}

export function removeStudentsFromClass(
  classId: number,
  studentIds: number[],
): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/students/detach`, {
    method: 'POST',
    body: { student_ids: studentIds },
  });
}
