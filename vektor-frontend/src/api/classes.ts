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

export function assignTeachers(classId: number, teacherIds: number[]): Promise<SchoolClass> {
  return apiRequest<SchoolClass>(`/classes/${classId}/teachers`, {
    method: 'POST',
    body: { teacher_ids: teacherIds },
  });
}
