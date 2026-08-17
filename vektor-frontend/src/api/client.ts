/**
 * Тонкая обёртка над fetch: базовый префикс /api, JSON, Bearer-токен,
 * нормализация ошибок. Все запросы к бэкенду идут через неё.
 */

const TOKEN_KEY = 'vektor_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** Разбор одного невалидного поля — из `errors` единого формата ошибок. */
export interface FieldError {
  /** Путь до поля, например `body.answers.0.value`. */
  field: string;
  message: string;
}

/**
 * Ошибка HTTP-уровня.
 *
 * Бэкенд отдаёт единый формат на все случаи (см. core/errors.py):
 * `{detail: string, code: string, errors?: FieldError[]}`. `detail` — всегда
 * строка, в том числе для 422, поэтому её можно показывать пользователю как
 * есть. `code` — машинный идентификатор: по нему различают причины, не
 * завязываясь на текст. `fieldErrors` заполняется только для валидации.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: FieldError[];

  constructor(status: number, message: string, code = '', fieldErrors: FieldError[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Запрос без Authorization-заголовка (логин, регистрация). */
  anonymous?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, anonymous = false } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const token = anonymous ? null : getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'Сервер недоступен. Проверьте соединение.');
  }

  if (!response.ok) {
    let detail = '';
    let code = '';
    let fieldErrors: FieldError[] = [];
    try {
      const data = await response.json();
      if (typeof data?.detail === 'string') detail = data.detail;
      if (typeof data?.code === 'string') code = data.code;
      if (Array.isArray(data?.errors)) fieldErrors = data.errors as FieldError[];
    } catch {
      // тело не JSON — оставляем generic-сообщение
    }
    throw new ApiError(
      response.status,
      detail || `Ошибка запроса (${response.status})`,
      code,
      fieldErrors,
    );
  }

  return (await response.json()) as T;
}
