import type { CompletedResult } from '../../types/dashboard';
import { Button } from '../ui/Button';
import './ResultCard.css';

interface ResultCardProps {
  result: CompletedResult;
  onView: (id: string) => void;
}

export function ResultCard({ result, onView }: ResultCardProps) {
  return (
    <div className="result-card">
      <div className="result-card__main">
        <div className="result-card__title">{result.testTitle}</div>
        <div className="result-card__meta">
          {result.competenciesCount} компетенций · {result.openedDateLabel}
        </div>
      </div>
      <div className="result-card__score">{result.averageScore.toFixed(1)}</div>
      <Button variant="secondary" onClick={() => onView(result.id)}>
        Посмотреть
      </Button>
    </div>
  );
}
