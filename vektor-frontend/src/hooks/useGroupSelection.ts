import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/** Число из query-параметра. Мусор («?class=abc») — как будто параметра нет. */
function numberParam(value: string | null): number | undefined {
  if (value === null || value === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * Что открыто на экране группы — класс и период — живёт в адресе страницы
 * (`?class=8&campaign=12`), а не в useState.
 *
 * Три причины именно так:
 * 1. Срез можно переслать («посмотри 8-1 за июнь 2025») — раньше ссылка
 *    открывала первый класс по сортировке и период по умолчанию.
 * 2. «Назад» в браузере возвращает предыдущий срез, а не уводит с экрана.
 * 3. Период физически не может пережить смену класса. Страница одна на все
 *    классы, и от состояния в useState период переезжал на следующий
 *    открытый класс; кампании у классов разные, поэтому чужой период давал
 *    пустой профиль, а перезагрузка страницы «чинила» его сама. Раньше это
 *    лечилось хранением пары {classId, campaignId} и сравнением в рендере —
 *    заплатка на том, что состояние лежало не там.
 *
 * Обе записи — replace: переключение класса и периода это работа внутри
 * экрана, и накапливать по записи в историю на каждый щелчок значило бы
 * сделать кнопку «назад» бесполезной для ухода со страницы.
 */
export function useGroupSelection() {
  const [params, setParams] = useSearchParams();

  const selectGroup = useCallback(
    (id: number) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('class', String(id));
          // Период принадлежит паре «класс + кампания»: у другого класса
          // кампании другие, и унесённый с собой период не нашёлся бы в
          // списке — экран показал бы пустоту вместо умолчания.
          next.delete('campaign');
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const selectCampaign = useCallback(
    (id: number) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('campaign', String(id));
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  /** Выбранной группы больше нет (класс удалён) — экран переедет на умолчание. */
  const clearGroup = useCallback(() => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('class');
        next.delete('campaign');
        return next;
      },
      { replace: true },
    );
  }, [setParams]);

  return {
    groupId: numberParam(params.get('class')),
    campaignId: numberParam(params.get('campaign')),
    selectGroup,
    selectCampaign,
    clearGroup,
  };
}
