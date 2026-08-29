import { useCallback, useMemo, useState } from 'react';

/**
 * Множественное выделение строк таблицы состава (классы, кейсы).
 *
 * Два решения, из-за которых это хук, а не `useState<Set<number>>` на месте:
 *
 * 1. **Выбор сбрасывается при смене `resetKey`** — вкладки или самого
 *    класса/кейса. Иначе можно открепить людей, которых на экране уже не
 *    видно: выделили трёх учеников, переключились на «Учителя», нажали
 *    «Открепить» — и ушли ученики другой вкладки.
 * 2. **`selectedIds` всегда пересекается с текущими строками.** После reload
 *    состав приходит новым, и id, которого в нём больше нет (открепил другой
 *    админ), не должен уехать в запрос — бэкенд ответит 409 на всю пачку.
 *    Пересечение считается на чтении, а не чисткой в эффекте: так нет окна,
 *    в котором состояние и данные разошлись.
 */
export function useRowSelection(rowIds: number[], resetKey: string) {
  const [checked, setChecked] = useState<Set<number>>(() => new Set());
  const [seenKey, setSeenKey] = useState(resetKey);

  // Сброс ПРЯМО В РЕНДЕРЕ, а не в useEffect: эффект отработал бы уже после
  // отрисовки, и один кадр таблица показывала бы галочки с прошлой вкладки.
  // Это документированный React-паттерн «adjust state during render» — он
  // перезапускает рендер до коммита, без каскада эффектов.
  if (seenKey !== resetKey) {
    setSeenKey(resetKey);
    setChecked(new Set());
  }

  // Порядок — как в таблице: список уходит в подтверждение открепления, и
  // читать его удобнее в том же порядке, что на экране.
  const selectedIds = useMemo(() => rowIds.filter((id) => checked.has(id)), [rowIds, checked]);

  const toggle = useCallback((id: number) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // Чекбокс в шапке: «выделить всё» пока выделены не все, иначе «снять всё».
  const toggleAll = useCallback(() => {
    setChecked((prev) => {
      const allChecked = rowIds.length > 0 && rowIds.every((id) => prev.has(id));
      return allChecked ? new Set() : new Set(rowIds);
    });
  }, [rowIds]);

  const clear = useCallback(() => setChecked(new Set()), []);

  return {
    selectedIds,
    count: selectedIds.length,
    has: (id: number) => checked.has(id),
    toggle,
    toggleAll,
    clear,
    allChecked: rowIds.length > 0 && selectedIds.length === rowIds.length,
    someChecked: selectedIds.length > 0 && selectedIds.length < rowIds.length,
  };
}

export type RowSelection = ReturnType<typeof useRowSelection>;
