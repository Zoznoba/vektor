import { Icon } from '../icons/Icon';
import { ScaleButtons } from './ScaleButtons';
import type { Chapter } from '../../pages/student/assessmentGrouping';
import './DenseChapters.css';

interface DenseChaptersProps {
  chapters: Chapter[];
  activeChapterId: number;
  onSelectChapter: (outcomeAreaId: number) => void;
  answers: Record<number, number>;
  onAnswer: (questionId: number, value: number) => void;
  onPrevChapter: () => void;
  onNextChapter: () => void;
  hasPrevChapter: boolean;
  hasNextChapter: boolean;
}

export function DenseChapters({
  chapters,
  activeChapterId,
  onSelectChapter,
  answers,
  onAnswer,
  onPrevChapter,
  onNextChapter,
  hasPrevChapter,
  hasNextChapter,
}: DenseChaptersProps) {
  const chapterIndex = chapters.findIndex((c) => c.outcomeAreaId === activeChapterId);
  const activeChapter = chapters[chapterIndex];
  if (!activeChapter) return null;
  const answeredInChapter = activeChapter.questions.filter((q) => answers[q.id] !== undefined).length;

  return (
    <div className="dense-chapters">
      <div className="dense-chapters__rail">
        {chapters.map((c, i) => {
          const answered = c.questions.filter((q) => answers[q.id] !== undefined).length;
          return (
            <button
              key={c.outcomeAreaId}
              type="button"
              className={`dense-chapters__rail-item ${
                c.outcomeAreaId === activeChapterId ? 'dense-chapters__rail-item--active' : ''
              }`.trim()}
              onClick={() => onSelectChapter(c.outcomeAreaId)}
            >
              <span className="dense-chapters__rail-num">{i + 1}</span>
              <span className="dense-chapters__rail-text">
                <span className="dense-chapters__rail-name">{c.name}</span>
                <span className="dense-chapters__rail-count">
                  {answered} / {c.questions.length}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="dense-chapters__panel">
        <div className="dense-chapters__panel-head">
          <span className="dense-chapters__panel-badge">
            Глава {chapterIndex + 1} из {chapters.length}
          </span>
          <span className="dense-chapters__panel-title">{activeChapter.name}</span>
          <span className="dense-chapters__panel-count">
            {answeredInChapter} / {activeChapter.questions.length}
          </span>
        </div>

        <div className="dense-chapters__questions">
          {activeChapter.questions.map((q) => (
            <div key={q.id} className="dense-chapters__question">
              <div className="dense-chapters__question-text">{q.text}</div>
              <ScaleButtons value={answers[q.id]} onSelect={(v) => onAnswer(q.id, v)} variant="dense" />
            </div>
          ))}
        </div>

        <div className="dense-chapters__panel-foot">
          <button
            type="button"
            className="dense-chapters__nav"
            onClick={onPrevChapter}
            disabled={!hasPrevChapter}
          >
            <Icon name="arrowLeft" size={13} />
            Предыдущая глава
          </button>
          <button
            type="button"
            className="dense-chapters__nav dense-chapters__nav--primary"
            onClick={onNextChapter}
            disabled={!hasNextChapter}
          >
            Следующая глава
            <Icon name="arrowRight" size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
