import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/client';

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** Перезапросить данные (после мутаций: создали пользователя — обновили список). */
  reload: () => void;
}

const INITIAL = { data: null, loading: true, error: null };

/**
 * Загрузка данных при монтировании + ручной reload.
 * fn обязана быть стабильной ссылкой (модульная функция из src/api/* или
 * useCallback) — она в зависимостях effect, нестабильная ссылка даст цикл
 * запросов.
 */
export function useApi<T>(fn: () => Promise<T>): ApiState<T> {
  const [state, setState] = useState<{
    data: T | null;
    loading: boolean;
    error: string | null;
  }>(INITIAL);
  // Счётчик перезагрузок: смена значения перезапускает effect
  const [version, setVersion] = useState(0);
  const [request, setRequest] = useState<{ fn: unknown; version: number }>({ fn, version });

  // Сброс состояния при смене запроса — в фазе рендера, а не в эффекте.
  // Иначе результат ПРОШЛОГО запроса доживал бы до следующего: экран, где fn
  // меняется вместе с параметром (выбрали другой класс), показывал бы ошибку
  // предыдущей загрузки поверх успешно пришедших данных.
  if (request.fn !== fn) {
    // Другой запрос — данные прошлого больше не про этот экран.
    setRequest({ fn, version });
    setState(INITIAL);
  } else if (request.version !== version) {
    // Тот же запрос заново (reload после мутации): данные оставляем на экране,
    // иначе список моргал бы пустотой после каждого сохранения.
    setRequest({ fn, version });
    setState((prev) => ({ ...prev, loading: true, error: null }));
  }

  useEffect(() => {
    let cancelled = false;

    fn()
      .then((result) => {
        if (cancelled) return;
        setState({ data: result, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          data: null,
          loading: false,
          error: err instanceof ApiError ? err.message : 'Не удалось загрузить данные',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [fn, version]);

  const reload = useCallback(() => {
    setVersion((v) => v + 1);
  }, []);

  return { ...state, reload };
}
