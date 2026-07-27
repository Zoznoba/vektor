import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './AuthContext';

/**
 * Обёртка защищённых маршрутов. Пока /users/me в полёте — ничего не рисуем
 * (иначе мигнёт редирект на логин у пользователя с валидным токеном).
 */
export function RequireAuth() {
  const { status } = useAuth();

  if (status === 'loading') return null;
  if (status === 'anonymous') return <Navigate to="/login" replace />;
  return <Outlet />;
}
