import { Icon } from '../icons/Icon';
import { Button } from '../ui/Button';
import './AssessmentSummary.css';

interface ChapterSummary {
  outcomeAreaId: number;
  name: string;
  total: number;
}

interface AssessmentSummaryProps {
  aboutLine: string;
  totalCount: number;
  chapters: ChapterSummary[];
  /** Идут несохранённые ответы — отправлять рано. */
  saving: boolean;
  onSubmit: () => void;
  onReview: () => void;
  /** Перейти к конкретной главе, если хочется перечитать именно её. */
  onSelectChapter: (outcomeAreaId: number) => void;
}

/**
 * Финал анкеты: все вопросы отвечены, показываем сводку и явную кнопку.
 *
 * Раньше последний ответ молча уводил на список анкет, и человек не понимал,
 * дошёл он до конца или что-то потерялось (ровно эта жалоба и привела к
 * экрану). Ответы при этом сохраняются по одному сразу, как и прежде: кнопка
 * ЗАВЕРШАЕТ просмотр, а не отправляет данные — поэтому текст говорит, что
 * ответы уже записаны, и закрытая вкладка ничего не теряет.
 */
export function AssessmentSummary({
  aboutLine,
  totalCount,
  chapters,
  saving,
  onSubmit,
  onReview,
  onSelectChapter,
}: AssessmentSummaryProps) {
  return (
    <div className="assessment-summary">
      <div className="assessment-summary__mark">
        <Icon name="check" size={26} />
      </div>

      <h3 className="assessment-summary__title">Анкета заполнена</h3>
      <div className="assessment-summary__sub">
        {aboutLine} · {totalCount} из {totalCount} вопросов
      </div>

      <div className="assessment-summary__chapters">
        {chapters.map((chapter) => (
          <button
            key={chapter.outcomeAreaId}
            type="button"
            className="assessment-summary__chapter"
            onClick={() => onSelectChapter(chapter.outcomeAreaId)}
          >
            <Icon name="check" size={13} />
            <span>{chapter.name}</span>
            <span className="assessment-summary__chapter-count">{chapter.total}</span>
          </button>
        ))}
      </div>

      <div className="assessment-summary__note">
        Ответы сохранены — если закроете страницу, ничего не потеряется. Можно вернуться и
        изменить любой из них.
      </div>

      <div className="assessment-summary__actions">
        <Button onClick={onSubmit} disabled={saving}>
          {saving ? 'Сохраняем…' : 'Отправить результаты'}
        </Button>
        <Button variant="secondary" onClick={onReview}>
          Проверить ответы
        </Button>
      </div>
    </div>
  );
}
