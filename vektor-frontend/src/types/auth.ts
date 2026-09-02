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
   * Кейс (профильная группа) — идентификатором, а не названием: бэкенд отдаёт
   * его в каждом UserOut как обычную колонку. Название экраны берут из
   * /cases, человеку в шапку его кладёт /users/me (case_name).
   */
  case_id?: number | null;
  /**
   * «8-1» — только у ученика; у учителя, родителя и админа класса нет.
   * Приходит из /users/me; в списках пользователей поля нет.
   */
  class_label?: string | null;
  /**
   * «2025/2026 учебный год» — считается на бэке от текущей даты, не привязан
   * к роли. Приходит из /users/me; в списках пользователей поля нет.
   */
  academic_year?: string;
  /** Название кейса — приходит только из /users/me, в списках его нет. */
  case_name?: string | null;
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
