/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/auth/schemas.py).
 * Контракт: UserOut и TokenOut. Менять синхронно с бэкендом.
 */

export type UserRole = 'student' | 'teacher' | 'parent' | 'admin';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  /**
   * «8-1» — только у ученика; у учителя, родителя и админа класса нет.
   * Приходит из /users/me; в списках пользователей поля нет.
   */
  class_label?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export const ROLE_LABELS: Record<UserRole, string> = {
  student: 'Ученик',
  teacher: 'Учитель',
  parent: 'Родитель',
  admin: 'Администратор',
};
