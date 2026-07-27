/**
 * Контекст авторизации: хранит текущего пользователя и токен.
 *
 * Жизненный цикл: при старте приложения, если в localStorage лежит токен,
 * дёргаем /users/me — пока запрос идёт, status === 'loading' (роуты ждут,
 * не редиректя на логин). Невалидный/протухший токен просто чистим.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError, clearToken, getToken, setToken } from '../api/client';
import * as authApi from '../api/auth';
import type { User } from '../types/auth';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(getToken() ? 'loading' : 'anonymous');
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;

    authApi
      .fetchMe()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        setStatus('authenticated');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // 401 — токен протух; сетевые ошибки тоже роняем в anonymous,
        // иначе приложение навсегда зависнет в 'loading'
        if (err instanceof ApiError && err.status === 401) clearToken();
        setUser(null);
        setStatus('anonymous');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password);
    setToken(access_token);
    const me = await authApi.fetchMe();
    setUser(me);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setStatus('anonymous');
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, login, logout }}>{children}</AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth должен вызываться внутри <AuthProvider>');
  return ctx;
}
