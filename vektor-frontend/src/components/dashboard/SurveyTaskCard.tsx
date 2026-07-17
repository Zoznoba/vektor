import type { PendingSurvey } from '../../types/dashboard';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ProgressBar } from '../ui/ProgressBar';
import './SurveyTaskCard.css';

interface SurveyTaskCardProps {
  survey: PendingSurvey;
  onAction: (id: string) => void;
}

export function SurveyTaskCard({ survey, onAction }: SurveyTaskCardProps) {
  const percent = Math.round((survey.answeredQuestions / survey.totalQuestions) * 100);
  const actionLabel = survey.status === 'not_started' ? 'Заполнить' : 'Продолжить';
  const buttonVariant = survey.status === 'not_started' ? 'primary' : 'secondary';

  return (
    <div className="survey-task-card">
      <div className="survey-task-card__main">
        <Badge variant="blue" className="survey-task-card__badge">
          {survey.badgeLabel}
        </Badge>
        <div className="survey-task-card__title">{survey.title}</div>
        <div className="survey-task-card__meta">
          <ProgressBar value={percent} className="survey-task-card__progress" />
          <span>
            {survey.answeredQuestions} из {survey.totalQuestions} вопросов
          </span>
        </div>
      </div>
      <Button variant={buttonVariant} onClick={() => onAction(survey.id)}>
        {actionLabel}
      </Button>
    </div>
  );
}
