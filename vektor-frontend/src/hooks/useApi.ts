import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/client';

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** Перезапросить данные (после мутаций: создали пользователя — обновили список). */
  reload: () => void;
}

/**
 * Загрузка данных при монтировании + ручной reload.
 * fn обязана быть стабильной ссылкой (модульная функция из src/api/*) —
 * она в зависимостях effect, нестабильная ссылка даст цикл запросов.
 */
export function useApi<T>(fn: () => Promise<T>): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Счётчик перезагрузок: смена значения перезапускает effect
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;

    fn()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Не удалось загрузить данные');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fn, version]);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setVersion((v) => v + 1);
  }, []);

  return { data, loading, error, reload };
}
