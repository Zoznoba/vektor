import { useState } from 'react';
import type { ReactNode } from 'react';
import { Icon } from '../icons/Icon';
import './Collapsible.css';

interface CollapsibleProps {
  title: string;
  /** Строка под заголовком: чем этот блок полезен, пока он свёрнут. */
  hint?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}

/**
 * Сворачиваемый блок с плавным раскрытием.
 *
 * Высота анимируется через `grid-template-rows: 0fr → 1fr`, а не через
 * max-height: содержимое здесь заранее неизвестной высоты (радар плюс список
 * зон роста, который ещё и приезжает позже загрузки), а подобранный на глаз
 * max-height либо режет длинный блок, либо даёт паузу в конце анимации на
 * коротком. Grid-переход считает реальную высоту сам.
 *
 * Содержимое монтируется при ПЕРВОМ раскрытии и дальше остаётся в DOM: так
 * данные не перезапрашиваются на каждое открытие, а сворачивание успевает
 * проиграться (при мгновенном размонтировании блок просто исчезал бы,
 * вместо того чтобы съезжаться).
 */
export function Collapsible({ title, hint, open, onToggle, children }: CollapsibleProps) {
  const [everOpened, setEverOpened] = useState(open);

  const handleToggle = () => {
    if (!open) setEverOpened(true);
    onToggle();
  };

  return (
    <section className={`collapsible ${open ? 'collapsible--open' : ''}`.trim()}>
      <button type="button" className="collapsible__head" onClick={handleToggle} aria-expanded={open}>
        <div className="collapsible__title">
          {title}
          {hint && <div className="collapsible__hint">{hint}</div>}
        </div>
        <Icon name="chevronDown" size={18} className="collapsible__chevron" />
      </button>

      <div className="collapsible__body">
        <div className="collapsible__inner">
          <div className="collapsible__content">{everOpened ? children : null}</div>
        </div>
      </div>
    </section>
  );
}
