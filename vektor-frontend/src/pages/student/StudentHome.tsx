import { useNavigate } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { InfoBanner } from '../../components/dashboard/InfoBanner';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import { useAuth } from '../../auth/AuthContext';
import { useApi } from '../../hooks/useApi';
import { fetchMyAssessments } from '../../api/assessments';
import type { AssessmentListItem } from '../../types/assessment';
import './StudentHome.css';

/** «Иванова Полина» → «Полина»; если слово одно — оно и есть имя. */
function firstNameOf(fullName: string): string {
  const words = fullName.trim().split(/\s+/);
  return words[1] ?? words[0];
}

/** Ближайший дедлайн среди незавершённых анкет, «20 июня» — или null, если ни у одной кампании нет closes_at. */
function nearestDeadlineLabel(pendingItems: AssessmentListItem[]): string | null {
  const deadlines = pendingItems
    .map((item) => item.campaign_closes_at)
    .filter((value): value is string => value !== null)
    .map((value) => new Date(value));
  if (deadlines.length === 0) return null;
  const nearest = new Date(Math.min(...deadlines.map((d) => d.getTime())));
  return nearest.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

/**
 * Экран 1 из ТЗ (п. 4.7) — «Личный кабинет ученика».
 *
 * Заполнение анкет отсюда ушло в раздел «Анкеты»: два места с одним и тем же
 * списком расходились бы по счётчикам. Здесь остаётся напоминание со ссылкой
 * туда и собственные результаты ученика.
 */
export function StudentHome() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const assessments = useApi(fetchMyAssessments);
  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const pendingItems = (assessments.data ?? []).filter((a) => a.status !== 'completed');
  const pendingCount = pendingItems.length;
  const deadlineLabel = nearestDeadlineLabel(pendingItems);

  return (
    <RoleShell activeNavKey="home">
      <h2>Добрый день, {firstNameOf(user.full_name)}</h2>
      <div className="app-main__sub">
        {user.class_label ? `${user.class_label} класс · ` : ''}
        {user.academic_year}
      </div>

      {pendingCount > 0 && (
        <InfoBanner actionLabel="Перейти к анкетам" onAction={() => navigate('/surveys')}>
          Ждут заполнения {pendingCount} {pendingCount === 1 ? 'анкета' : 'анкеты'}
          {deadlineLabel ? ` — дедлайн ${deadlineLabel}` : ''}
        </InfoBanner>
      )}

      <StudentResultsPanel subjectId={user.id} />
    </RoleShell>
  );
}
