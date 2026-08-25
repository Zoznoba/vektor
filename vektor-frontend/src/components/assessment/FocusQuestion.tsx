import { useEffect, useRef } from 'react';
import { Icon } from '../icons/Icon';
import { ScaleButtons } from './ScaleButtons';
import './FocusQuestion.css';

interface FocusQuestionProps {
  chapterName: string;
  chapterNum: number;
  chapterCount: number;
  qNumInChapter: number;
  qTotalInChapter: number;
  aboutLine: string;
  questionText: string;
  value: number | undefined;
  onSelect: (value: number) => void;
  onBack: () => void;
  onSkip: () => void;
  canGoBack: boolean;
  canSkip: boolean;
  /** Ключ вопроса — при смене поле перехватывает фокус для клавиш 1–5. */
  questionKey: number;
}

export function FocusQuestion({
  chapterName,
  chapterNum,
  chapterCount,
  qNumInChapter,
  qTotalInChapter,
  aboutLine,
  questionText,
  value,
  onSelect,
  onBack,
  onSkip,
  canGoBack,
  canSkip,
  questionKey,
}: FocusQuestionProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    cardRef.current?.focus();
  }, [questionKey]);

  const percent = qTotalInChapter > 0 ? Math.round((qNumInChapter / qTotalInChapter) * 100) : 0;

  return (
    <div
      className="focus-question"
      ref={cardRef}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key >= '1' && e.key <= '5') onSelect(Number(e.key));
      }}
    >
      <div className="focus-question__head">
        <span className="focus-question__badge">
          Глава {chapterNum} из {chapterCount} · {chapterName}
        </span>
        <span className="focus-question__counter">
          Вопрос {qNumInChapter} из {qTotalInChapter}
        </span>
      </div>
      <div className="focus-question__bar-track">
        <div className="focus-question__bar" style={{ width: `${percent}%` }} />
      </div>

      <div className="focus-question__body" key={questionKey}>
        <div className="focus-question__about">{aboutLine}</div>
        <div className="focus-question__text">{questionText}</div>
        <ScaleButtons value={value} onSelect={onSelect} variant="focus" />
        <div className="focus-question__hint">
          <span>
            <Icon name="check" size={13} />
            Клавиши 1–5 · сохраняется автоматически
          </span>
        </div>
      </div>

      <div className="focus-question__foot">
        <button type="button" className="focus-question__nav" onClick={onBack} disabled={!canGoBack}>
          <Icon name="arrowLeft" size={13} />
          Назад
        </button>
        <button
          type="button"
          className="focus-question__skip"
          onClick={onSkip}
          disabled={!canSkip}
        >
          Пропустить
          <Icon name="arrowRight" size={13} />
        </button>
      </div>
    </div>
  );
}
