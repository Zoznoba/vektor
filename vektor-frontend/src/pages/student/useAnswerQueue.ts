import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react';
import { ApiError } from '../../api/client';
import { submitAnswers } from '../../api/assessments';

/** Пауза без ответов, после которой накопленное уходит на сервер. */
const IDLE_MS = 1200;
/** Максимум времени, которое ответ ждёт в очереди, даже если человек тараторит. */
const MAX_WAIT_MS = 6000;
/** Столько ответов отправляем не дожидаясь паузы (глава анкеты — 3 вопроса). */
const BATCH_SIZE = 5;
/** Через столько повторяем попытку после сетевой ошибки. */
const RETRY_MS = 5000;

export interface AnswerQueue {
  /** Поставить ответ в очередь (перезаписывает прежний ответ на тот же вопрос). */
  enqueue: (questionId: number, value: number) => void;
  /** Отправить накопленное немедленно. */
  flush: () => void;
  /** Есть неотправленные ответы или запрос в полёте. */
  saving: boolean;
  /** Последняя ошибка сохранения; очищается при успешной отправке. */
  error: string | null;
}

/**
 * Накопитель ответов: собирает пачку и отправляет её одним запросом.
 *
 * До этого каждый клик по шкале дёргал POST /assessments/{id}/answers — на
 * анкете из 33 вопросов это 33 запроса на человека, а анкеты заполняют
 * классом одновременно. Эндпоинт с Этапа 4d принимает частичные пачки и
 * upsert'ит, поэтому батчинг целиком фронтовый: бэкенд не тронут.
 *
 * Автосохранение при этом остаётся автосохранением — кнопки «Сохранить» нет,
 * и вкладку закрывают в любой момент. Отсюда четыре независимых повода
 * отправить пачку: пауза в ответах (IDLE_MS), накопилось BATCH_SIZE, ответ
 * ждёт дольше MAX_WAIT_MS (иначе быстрый человек, отвечающий без пауз, довёз
 * бы всю анкету в памяти вкладки) и уход со страницы (visibilitychange /
 * pagehide / размонтирование) — там fetch идёт с `keepalive`, обычный запрос
 * браузер убил бы вместе со страницей.
 *
 * Очередь — Map questionId → value, поэтому повторный ответ на тот же вопрос
 * не копится, а заменяет прежний. Запросы сериализованы (`inFlight`): без
 * этого два ответа на один вопрос, ушедшие параллельно, легли бы в БД в
 * произвольном порядке. Неудачная отправка возвращает ответы в очередь, но
 * НЕ затирает то, что человек успел поменять за время запроса.
 */
export function useAnswerQueue(assessmentId: number): AnswerQueue {
  const queue = useRef(new Map<number, number>());
  const inFlight = useRef(false);
  const idleTimer = useRef<number | null>(null);
  const maxWaitTimer = useRef<number | null>(null);
  const retryTimer = useRef<number | null>(null);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clearTimer = (ref: MutableRefObject<number | null>) => {
    if (ref.current !== null) {
      window.clearTimeout(ref.current);
      ref.current = null;
    }
  };

  // Отложенные отправки (повтор после ошибки, «хвост» накопленного за время
  // запроса) зовут send из него самого — через ref, иначе useCallback
  // ссылался бы на себя до объявления.
  const sendRef = useRef<(keepalive: boolean) => void>(() => {});

  const send = useCallback(
    async (keepalive: boolean) => {
      if (inFlight.current || queue.current.size === 0) return;

      clearTimer(idleTimer);
      clearTimer(maxWaitTimer);
      clearTimer(retryTimer);

      const batch = [...queue.current.entries()].map(([question_id, value]) => ({
        question_id,
        value,
      }));
      queue.current.clear();
      inFlight.current = true;

      try {
        await submitAnswers(assessmentId, batch, { keepalive });
        setError(null);
      } catch (err: unknown) {
        // Вернуть в очередь, не затирая более свежие ответы на те же вопросы.
        for (const { question_id, value } of batch) {
          if (!queue.current.has(question_id)) queue.current.set(question_id, value);
        }
        setError(err instanceof ApiError ? err.message : 'Не удалось сохранить ответы');
        retryTimer.current = window.setTimeout(() => sendRef.current(false), RETRY_MS);
      } finally {
        inFlight.current = false;
        setSaving(queue.current.size > 0);
      }

      // За время запроса могли накопиться новые ответы — отправляем следом.
      if (queue.current.size > 0 && retryTimer.current === null) {
        clearTimer(idleTimer);
        idleTimer.current = window.setTimeout(() => sendRef.current(false), IDLE_MS);
      }
    },
    [assessmentId],
  );

  useEffect(() => {
    sendRef.current = (keepalive: boolean) => void send(keepalive);
  }, [send]);

  const flush = useCallback(() => void send(false), [send]);

  const enqueue = useCallback(
    (questionId: number, value: number) => {
      queue.current.set(questionId, value);
      setSaving(true);
      setError(null);
      clearTimer(retryTimer);

      if (queue.current.size >= BATCH_SIZE) {
        void send(false);
        return;
      }

      clearTimer(idleTimer);
      idleTimer.current = window.setTimeout(() => void send(false), IDLE_MS);
      if (maxWaitTimer.current === null) {
        maxWaitTimer.current = window.setTimeout(() => void send(false), MAX_WAIT_MS);
      }
    },
    [send],
  );

  // Уход со страницы: вкладку свернули, закрыли или ушли на другой роут.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === 'hidden') void send(true);
    };
    const onPageHide = () => void send(true);
    // Без диалога «точно уйти?»: keepalive-запрос переживает закрытие
    // вкладки сам, а лишнее подтверждение на анкете только пугает.
    const onBeforeUnload = () => void send(true);

    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('pagehide', onPageHide);
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      document.removeEventListener('visibilitychange', onHide);
      window.removeEventListener('pagehide', onPageHide);
      window.removeEventListener('beforeunload', onBeforeUnload);
      clearTimer(idleTimer);
      clearTimer(maxWaitTimer);
      clearTimer(retryTimer);
      void send(true);
    };
  }, [send]);

  return { enqueue, flush, saving, error };
}
