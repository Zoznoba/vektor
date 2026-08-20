import { useNavigate } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { Panel } from '../../components/ui/Panel';
import { SurveyTaskCard } from '../../components/dashboard/SurveyTaskCard';
import { useApi } from '../../hooks/useApi';
import { fetchMyAssessments } from '../../api/assessments';
import type { AssessmentListItem, RaterRole } from '../../types/assessment';
import type { PendingSurvey } from '../../types/dashboard';

/**
 * Подпись роли оценивающего.
 *
 * Ключ — rater_role анкеты, а НЕ роль залогиненного пользователя: учитель
 * может оценивать и как родитель собственного ребёнка, и тогда «Оценить
 * ученика» будет враньём. Роль фиксируется при генерации анкеты и переживает
 * перевод ученика в следующий класс.
 */
const RATER_ACTION_LABEL: Record<RaterRole, string> = {
  self: 'Самооценка',
  peer: 'Оценить одноклассника',
  teacher: 'Оценить ученика',
  parent: 'Оценить ребёнка',
};

/**
 * Анкета → карточка. Бэк отдаёт сырые данные (роль ратора, субъект, кампания),
 * текст под UI собираем здесь: это вопрос представления, не домена.
 */
function toPendingSurvey(item: AssessmentListItem): PendingSurvey {
  return {
    id: String(item.id),
    badgeLabel: `${RATER_ACTION_LABEL[item.rater_role]} · ${item.campaign_title}`,
    title: item.is_self ? 'Самооценка' : item.subject.full_name,
    totalQuestions: item.total_questions,
    answeredQuestions: item.answered_questions,
    // completed сюда не попадает — отфильтровано до вызова маппера.
    status: item.status as 'not_started' | 'in_progress',
  };
}

/**
 * Раздел «Анкеты» — единственное место, где заполняются анкеты.
 *
 * Общий для всех ролей: список строится по /assessments, то есть по тому, где
 * пользователь стоит респондентом. Учителю сюда попадают анкеты про его
 * учеников, ученику — самооценка и одноклассники, родителю — его дети.
 */
export function SurveysPage() {
  const navigate = useNavigate();
  const assessments = useApi(fetchMyAssessments);

  const items = assessments.data ?? [];
  const pending = items.filter((a) => a.status !== 'completed').map(toPendingSurvey);
  const completedCount = items.length - pending.length;

  const handleFillSurvey = (id: string) => {
    navigate(`/assessments/${id}`);
  };

  return (
    <RoleShell activeNavKey="surveys">
      <h2>Анкеты</h2>
      <div className="app-main__sub">
        {pending.length > 0
          ? `Ждут заполнения: ${pending.length}`
          : 'Все анкеты заполнены'}
        {completedCount > 0 ? ` · завершено: ${completedCount}` : ''}
      </div>

      <Panel title="Анкеты для заполнения">
        {assessments.error && <div className="form-error">{assessments.error}</div>}
        {assessments.loading ? (
          <div className="app-main__sub">Загрузка…</div>
        ) : pending.length === 0 ? (
          <div className="app-main__sub">Анкет, ожидающих заполнения, нет</div>
        ) : (
          pending.map((survey) => (
            <SurveyTaskCard key={survey.id} survey={survey} onAction={handleFillSurvey} />
          ))
        )}
      </Panel>
    </RoleShell>
  );
}
