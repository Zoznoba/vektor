import { AppShell } from '../../components/layout/AppShell';
import { STUDENT_NAV_ITEMS } from '../../data/navigation';
import { InfoBanner } from '../../components/dashboard/InfoBanner';
import { Panel } from '../../components/ui/Panel';
import { SurveyTaskCard } from '../../components/dashboard/SurveyTaskCard';
import { ResultCard } from '../../components/dashboard/ResultCard';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABELS } from '../../types/auth';
import {
  mockCompletedResults,
  mockPendingSurveys,
  mockStudent,
} from '../../data/mockStudentDashboard';

/** «Иванова Полина» → «Полина»; если слово одно — оно и есть имя. */
function firstNameOf(fullName: string): string {
  const words = fullName.trim().split(/\s+/);
  return words[1] ?? words[0];
}

/**
 * Экран 1 из ТЗ (п. 4.7) — «Личный кабинет ученика».
 * Пользователь — реальный (/users/me). Данные дашборда (анкеты, результаты)
 * пока на моках: их API появится на этапах 4–5 бэкенда; класс и учебный год
 * тоже мок — /users/me их пока не отдаёт.
 */
export function StudentHome() {
  const { user, logout } = useAuth();
  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const pendingCount = mockPendingSurveys.length;
  const nearestDeadlineLabel = '20 июня'; // TODO: брать минимальный deadline из реальных tests_360

  const handleNavigate = (key: string) => {
    if (key === 'home') return;
    // Остальные разделы пока не реализованы — здесь будет переход на страницу.
    console.info(`Раздел «${key}» пока не реализован`);
  };

  const handleFillSurvey = (id: string) => {
    console.info(`Открыть прохождение анкеты: ${id}`);
  };

  const handleViewResult = (id: string) => {
    console.info(`Открыть результат: ${id}`);
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
        {mockStudent.className} · {mockStudent.academicYear}
      </div>

      {pendingCount > 0 && (
        <InfoBanner actionLabel="Заполнить" onAction={() => handleFillSurvey(mockPendingSurveys[0].id)}>
          Ждут заполнения {pendingCount} {pendingCount === 1 ? 'анкета' : 'анкеты'} — дедлайн{' '}
          {nearestDeadlineLabel}
        </InfoBanner>
      )}

      <Panel title="Анкеты для заполнения">
        {mockPendingSurveys.map((survey) => (
          <SurveyTaskCard key={survey.id} survey={survey} onAction={handleFillSurvey} />
        ))}
      </Panel>

      <Panel title="Мои результаты">
        {mockCompletedResults.map((result) => (
          <ResultCard key={result.id} result={result} onView={handleViewResult} />
        ))}
      </Panel>
    </AppShell>
  );
}
