import { apiRequest } from './client';
import type { User, UserRole } from '../types/auth';

export function fetchUsers(): Promise<User[]> {
  return apiRequest<User[]>('/users');
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

export function fetchChildren(parentId: number): Promise<User[]> {
  return apiRequest<User[]>(`/users/${parentId}/children`);
}

export function assignChildren(parentId: number, childIds: number[]): Promise<unknown> {
  return apiRequest(`/users/${parentId}/children`, {
    method: 'POST',
    body: { child_ids: childIds },
  });
}
