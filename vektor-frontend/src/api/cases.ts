import { apiRequest } from './client';
import type { Case } from '../types/case';

export function fetchCases(): Promise<Case[]> {
  return apiRequest<Case[]>('/cases');
}

export function createCase(name: string, description: string | null): Promise<Case> {
  return apiRequest<Case>('/cases', { method: 'POST', body: { name, description } });
}

/**
 * Частичная правка. Отправляем только то, что меняем: бэкенд различает
 * «ключа нет» (не трогать) и `description: null` (стереть) — тот же контракт,
 * что у updateTeacherInClass.
 */
export function updateCase(
  caseId: number,
  changes: { name?: string; description?: string | null },
): Promise<Case> {
  return apiRequest<Case>(`/cases/${caseId}`, { method: 'PATCH', body: changes });
}

export function assignCaseStudents(caseId: number, userIds: number[]): Promise<Case> {
  return apiRequest<Case>(`/cases/${caseId}/students`, {
    method: 'POST',
    body: { user_ids: userIds },
  });
}

export function assignCaseTeachers(caseId: number, userIds: number[]): Promise<Case> {
  return apiRequest<Case>(`/cases/${caseId}/teachers`, {
    method: 'POST',
    body: { user_ids: userIds },
  });
}

/**
 * Открепление участников (учеников и учителей — ручка одна, бэкенд различает
 * их по роли). Всегда bulk, даже для одного человека: одиночный DELETE на
 * бэкенде остался, но два пути на фронте только разъехались бы.
 *
 * Атомарно на бэкенде: если хоть кого-то из списка в кейсе нет, не
 * открепляется никто. POST, а не DELETE, потому что тело у DELETE режут прокси.
 */
export function removeCaseMembers(caseId: number, userIds: number[]): Promise<Case> {
  return apiRequest<Case>(`/cases/${caseId}/members/detach`, {
    method: 'POST',
    body: { user_ids: userIds },
  });
}

/** Удалить можно только ПУСТОЙ кейс — иначе бэкенд отвечает 409. */
export function deleteCase(caseId: number): Promise<void> {
  return apiRequest<void>(`/cases/${caseId}`, { method: 'DELETE' });
}
