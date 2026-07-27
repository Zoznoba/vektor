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

/** Ошибка HTTP-уровня: статус + detail из тела FastAPI, если было. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
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
    try {
      const data = await response.json();
      if (typeof data?.detail === 'string') detail = data.detail;
    } catch {
      // тело не JSON — оставляем generic-сообщение
    }
    throw new ApiError(response.status, detail || `Ошибка запроса (${response.status})`);
  }

  return (await response.json()) as T;
}
