import { useEffect, useRef } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import { Icon } from '../icons/Icon';
import './Modal.css';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/** Модальное окно: клик по подложке или Esc закрывают. */
export function Modal({ title, onClose, children }: ModalProps) {
  /**
   * Закрываем, только если жест начался И закончился на подложке.
   * Иначе выделение текста в поле, отпущенное за пределами окна, всплывало бы
   * как click на подложке (target у click — общий предок mousedown/mouseup)
   * и закрывало модалку прямо во время правки значения.
   */
  const pressedOnOverlay = useRef(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleOverlayMouseDown = (e: MouseEvent<HTMLDivElement>) => {
    pressedOnOverlay.current = e.target === e.currentTarget;
  };

  const handleOverlayClick = (e: MouseEvent<HTMLDivElement>) => {
    const startedAndEndedOnOverlay = pressedOnOverlay.current && e.target === e.currentTarget;
    pressedOnOverlay.current = false;
    if (startedAndEndedOnOverlay) onClose();
  };

  return (
    <div
      className="modal-overlay"
      onMouseDown={handleOverlayMouseDown}
      onClick={handleOverlayClick}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal__head">
          <h3>{title}</h3>
          <button className="modal__close" onClick={onClose} aria-label="Закрыть">
            <Icon name="x" size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
