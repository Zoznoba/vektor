import { useNavigate } from 'react-router-dom';
import { AppShell } from '../../components/layout/AppShell';
import { STUDENT_NAV_ITEMS } from '../../data/navigation';
import { InfoBanner } from '../../components/dashboard/InfoBanner';
import { Panel } from '../../components/ui/Panel';
import { SurveyTaskCard } from '../../components/dashboard/SurveyTaskCard';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABELS } from '../../types/auth';
import { useApi } from '../../hooks/useApi';
import { fetchMyAssessments } from '../../api/assessments';
import type { AssessmentListItem } from '../../types/assessment';
import type { PendingSurvey } from '../../types/dashboard';
import { mockStudent } from '../../data/mockStudentDashboard';
import './StudentHome.css';

/** «Иванова Полина» → «Полина»; если слово одно — оно и есть имя. */
function firstNameOf(fullName: string): string {
  const words = fullName.trim().split(/\s+/);
  return words[1] ?? words[0];
}

/**
 * Анкета → карточка на дашборде. Бэк отдаёт сырые данные (is_self, субъект,
 * кампания) — текст под UI (бейдж/заголовок) собираем здесь, а не на бэке:
 * это вопрос представления, не домена.
 */
function toPendingSurvey(item: AssessmentListItem): PendingSurvey {
  return {
    id: String(item.id),
    badgeLabel: item.is_self
      ? `Самооценка · ${item.campaign_title}`
      : `Оценить одноклассника · ${item.campaign_title}`,
    title: item.is_self ? 'Самооценка' : `Опрос: ${item.subject.full_name}`,
    totalQuestions: item.total_questions,
    answeredQuestions: item.answered_questions,
    // completed сюда не попадает — отфильтровано до вызова маппера.
    status: item.status as 'not_started' | 'in_progress',
  };
}

/**
 * Экран 1 из ТЗ (п. 4.7) — «Личный кабинет ученика».
 * Пользователь, анкеты и результаты — реальные (/users/me, /assessments,
 * /results). Класс и учебный год всё ещё мок: /users/me их не отдаёт.
 */
export function StudentHome() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const assessments = useApi(fetchMyAssessments);
  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const pending = (assessments.data ?? [])
    .filter((a) => a.status !== 'completed')
    .map(toPendingSurvey);
  const pendingCount = pending.length;
  const nearestDeadlineLabel = '20 июня'; // TODO: брать минимальный deadline из реальных campaign.closes_at

  const handleNavigate = (key: string) => {
    if (key === 'home') return;
    // Остальные разделы пока не реализованы — здесь будет переход на страницу.
    console.info(`Раздел «${key}» пока не реализован`);
  };

  const handleFillSurvey = (id: string) => {
    navigate(`/assessments/${id}`);
  };

  return (
    <AppShell
      navItems={STUDENT_NAV_ITEMS}
      activeNavKey="home"
      onNavigate={handleNavigate}
      userFullName={user.full_name}
      userRoleLabel={ROLE_LABELS[user.role]}
      onLogout={logout}
    >
      <h2>Добрый день, {firstNameOf(user.full_name)}</h2>
      <div className="app-main__sub">
        {/* Класс — реальный, из /users/me. Учебный год пока мок: его нигде
            в модели нет, кампания знает только period. */}
        {user.class_label ? `${user.class_label} класс · ` : ''}
        {mockStudent.academicYear}
      </div>

      {pendingCount > 0 && (
        <InfoBanner actionLabel="Заполнить" onAction={() => handleFillSurvey(pending[0].id)}>
          Ждут заполнения {pendingCount} {pendingCount === 1 ? 'анкета' : 'анкеты'} — дедлайн{' '}
          {nearestDeadlineLabel}
        </InfoBanner>
      )}

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

      <StudentResultsPanel subjectId={user.id} />

    </AppShell>
  );
}
