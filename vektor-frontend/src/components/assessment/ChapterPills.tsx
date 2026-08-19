import './ChapterPills.css';

interface ChapterSummary {
  outcomeAreaId: number;
  name: string;
  answered: number;
  total: number;
}

interface ChapterPillsProps {
  chapters: ChapterSummary[];
  activeChapterId: number | undefined;
  onSelect: (outcomeAreaId: number) => void;
  answeredCount: number;
  totalCount: number;
}

export function ChapterPills({
  chapters,
  activeChapterId,
  onSelect,
  answeredCount,
  totalCount,
}: ChapterPillsProps) {
  return (
    <div className="chapter-pills">
      <div className="chapter-pills__list">
        {chapters.map((c, i) => (
          <button
            key={c.outcomeAreaId}
            type="button"
            title={c.name}
            className={`chapter-pills__item ${
              c.outcomeAreaId === activeChapterId ? 'chapter-pills__item--active' : ''
            } ${c.answered === c.total ? 'chapter-pills__item--done' : ''}`.trim()}
            onClick={() => onSelect(c.outcomeAreaId)}
          >
            {i + 1}
          </button>
        ))}
      </div>
      <span className="chapter-pills__summary">
        {answeredCount} / {totalCount}
      </span>
    </div>
  );
}
