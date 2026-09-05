import { apiRequest } from './client';
import type { User, UserRole } from '../types/auth';

export interface FetchUsersParams {
  role?: UserRole;
  search?: string;
  classId?: number;
  caseId?: number;
  /** Только те, кто не состоит НИ В ОДНОМ кейсе — кандидаты на привязку. */
  withoutCase?: boolean;
}

export function fetchUsers(params: FetchUsersParams = {}): Promise<User[]> {
  const query = new URLSearchParams();
  if (params.role) query.set('role', params.role);
  if (params.search) query.set('search', params.search);
  if (params.classId !== undefined) query.set('class_id', String(params.classId));
  if (params.caseId !== undefined) query.set('case_id', String(params.caseId));
  if (params.withoutCase) query.set('without_case', 'true');
  const qs = query.toString();
  return apiRequest<User[]>(`/users${qs ? `?${qs}` : ''}`);
}

export interface CreateUserIn {
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
}

/**
 * Создание пользователя админом. Бэкенд пока переиспользует открытый
 * /auth/register (закрыть его от самостоятельной регистрации — задача
 * бэкенда, Этап 7); фронт уже ходит как «админ создаёт учётку».
 */
export function createUser(data: CreateUserIn): Promise<User> {
  return apiRequest<User>('/auth/register', { method: 'POST', body: data });
}

export interface BulkUserIn {
  email: string;
  full_name: string;
  role: UserRole;
}

export interface BulkCreateResult {
  created: User[];
  class_id: number | null;
  case_id: number | null;
  /**
   * ВРЕМЕННО: общий пароль, которым заведены все юзеры пачки (эхом с бэка).
   * Показываем админу один раз, чтобы было чем залогиниться на тестах —
   * уедет, когда бэк включит авто-генерацию + рассылку паролей.
   */
  default_password: string;
}

/**
 * Массовое создание пользователей одним атомарным вызовом (Этап 3.7).
 * classId привязывает к классу строки с role=student; caseId кладёт в кейс
 * И учеников, И учителей — членство в кейсе одно на обе роли.
 */
export function bulkCreateUsers(
  users: BulkUserIn[],
  classId?: number | null,
  caseId?: number | null,
): Promise<BulkCreateResult> {
  return apiRequest<BulkCreateResult>('/users/bulk', {
    method: 'POST',
    body: { class_id: classId ?? null, case_id: caseId ?? null, users },
  });
}

/**
 * Включить/выключить учётку — единственная форма «удаления» пользователя:
 * скрывает его и блокирует вход, но сохраняет всю историю (ответы анкет,
 * привязки к классу/детям).
 */
export function setUserActive(userId: number, isActive: boolean): Promise<User> {
  return apiRequest<User>(`/users/${userId}/active`, {
    method: 'PATCH',
    body: { is_active: isActive },
  });
}

/**
 * Сбросить пароль пользователя. Почтовой рассылки в системе нет — новый
 * пароль приходит в ответе один раз, показать его повторно нельзя.
 */
export function resetPassword(userId: number): Promise<{ new_password: string }> {
  return apiRequest<{ new_password: string }>(`/users/${userId}/reset-password`, {
    method: 'POST',
  });
}

export function fetchChildren(parentId: number): Promise<User[]> {
  return apiRequest<User[]>(`/users/${parentId}/children`);
}

export function assignChildren(parentId: number, childIds: number[]): Promise<unknown> {
  return apiRequest(`/users/${parentId}/children`, {
    method: 'POST',
    body: { child_ids: childIds },
  });
}
