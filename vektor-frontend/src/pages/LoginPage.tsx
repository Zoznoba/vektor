import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../api/client';
import { Button } from '../components/ui/Button';
import logoWhite from '../assets/logo-white.png';
import './LoginPage.css';

/**
 * Экран входа (концепт: вкладка «Вход»). Слева — брендовая панель с градиентом
 * и белым логотипом, справа — форма email + пароль. Самостоятельной регистрации
 * нет: учётки создаёт администратор школы.
 */
export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Неверный email или пароль');
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Что-то пошло не так. Попробуйте ещё раз.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <aside className="login-brand">
        <img src={logoWhite} alt="Школа Вектор" />
        <p>
          Платформа развития
          <br />
          учеников школы Вектор
        </p>
      </aside>

      <main className="login-form-wrap">
        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <h1>Вход</h1>
          <p className="login-form__desc">
            Используйте email и пароль, выданные администратором школы
          </p>

          <label className="login-field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              placeholder="имя@shkola-vektor.ru"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </label>

          <label className="login-field">
            <span>Пароль</span>
            <input
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <Button type="submit" variant="primary" block disabled={submitting}>
            {submitting ? 'Входим…' : 'Войти'}
          </Button>

          <p className="login-note">
            Доступ к платформе предоставляется по приглашению — администратор школы создаёт
            учётную запись и отправляет ссылку для входа
          </p>
        </form>
      </main>
    </div>
  );
}
