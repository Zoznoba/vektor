import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { Button } from './Button';
import type { RowSelection } from '../../hooks/useRowSelection';
import './SelectionBar.css';

/**
 * Чекбокс «выделить всё» в шапке таблицы.
 *
 * Отдельный компонент только ради `indeterminate`: это не атрибут, а свойство
 * DOM-узла, из JSX его не выставить — нужен ref. Состояние «выделены не все»
 * важно: без него шапка при частичном выборе выглядит как «не выбрано ничего».
 */
export function SelectAllCheckbox({
  selection,
  label = 'Выделить все строки',
}: {
  selection: RowSelection;
  label?: string;
}) {
  const ref = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = selection.someChecked;
  }, [selection.someChecked]);

  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      checked={selection.allChecked}
      onChange={selection.toggleAll}
    />
  );
}

/**
 * Панель массовых действий над выделенными строками. Рендерится ТОЛЬКО когда
 * что-то выделено — пустая полоса «Выбрано 0» занимала бы место и мигала при
 * каждом снятии галочки.
 */
export function SelectionBar({
  selection,
  itemLabel,
  children,
}: {
  selection: RowSelection;
  /** Склонённое «5 учеников» — считает вызывающая сторона, слова разные. */
  itemLabel: (n: number) => string;
  children: ReactNode;
}) {
  if (selection.count === 0) return null;

  return (
    <div className="selection-bar">
      <span className="selection-bar__count">Выбрано: {itemLabel(selection.count)}</span>
      <div className="selection-bar__actions">{children}</div>
      <Button variant="secondary" onClick={selection.clear}>
        Снять выделение
      </Button>
    </div>
  );
}
