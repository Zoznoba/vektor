import './ScaleButtons.css';

const SCALE = [1, 2, 3, 4, 5];

/**
 * Подписи шкалы 1–5. В прототипе (`ref/Платформа Вектор.dc.html`, isSurvey)
 * подписи — динамическая переменная `{{ o.label }}` без зафиксированного
 * текста, конкретные формулировки не источник истины. Текст ниже — рабочий
 * вариант для симметричной шкалы Лайкерта, можно скорректировать по запросу.
 */
const SCALE_LABELS: Record<number, string> = {
  1: 'Совсем не проявляется',
  2: 'Скорее не проявляется',
  3: 'Проявляется иногда',
  4: 'Проявляется часто',
  5: 'Проявляется ярко',
};

interface ScaleButtonsProps {
  value: number | undefined;
  onSelect: (value: number) => void;
  variant?: 'focus' | 'dense';
}

export function ScaleButtons({ value, onSelect, variant = 'dense' }: ScaleButtonsProps) {
  return (
    <div className={`scale-buttons scale-buttons--${variant}`}>
      {SCALE.map((v) => (
        <button
          key={v}
          type="button"
          title={variant === 'dense' ? SCALE_LABELS[v] : undefined}
          className={`scale-buttons__option ${
            value === v ? 'scale-buttons__option--selected' : ''
          }`.trim()}
          onClick={() => onSelect(v)}
        >
          <span className="scale-buttons__num">{v}</span>
          {variant === 'focus' && <span className="scale-buttons__label">{SCALE_LABELS[v]}</span>}
        </button>
      ))}
    </div>
  );
}
