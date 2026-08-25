import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import './ActionMenu.css';

export interface ActionMenuItem {
  key: string;
  label: string;
  onSelect: () => void;
  /** Опасное действие (открепить) — красным и последним в списке. */
  danger?: boolean;
  disabled?: boolean;
}

/**
 * Дропдаун контекстных действий над строкой таблицы.
 *
 * Меню рендерится ВНУТРИ строки, а не порталом в body: строк на экране
 * немного, таблица не скроллится горизонтально, и позиционировать
 * абсолютом относительно ячейки достаточно — портал понадобился бы только
 * ради overflow:hidden у контейнера, которого здесь нет.
 */
export function ActionMenu({ items, trigger }: { items: ActionMenuItem[]; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();

  // Закрытие по клику мимо и по Escape — обработчики висят только пока меню
  // открыто, иначе каждая строка таблицы держала бы свой слушатель на document.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="action-menu" ref={rootRef}>
      <button
        type="button"
        className="action-menu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((prev) => !prev);
        }}
      >
        {trigger}
      </button>

      {open && (
        <div className="action-menu__list" id={menuId} role="menu">
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              className={`action-menu__item ${
                item.danger ? 'action-menu__item--danger' : ''
              }`.trim()}
              disabled={item.disabled}
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
