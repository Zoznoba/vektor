import { AppShell } from '../../components/layout/AppShell';
import { STUDENT_NAV_ITEMS } from '../../data/navigation';
import { InfoBanner } from '../../components/dashboard/InfoBanner';
import { Panel } from '../../components/ui/Panel';
import { SurveyTaskCard } from '../../components/dashboard/SurveyTaskCard';
import { ResultCard } from '../../components/dashboard/ResultCard';
import {
  mockCompletedResults,
  mockPendingSurveys,
  mockStudent,
} from '../../data/mockStudentDashboard';

/**
 * Экран 1 из ТЗ (п. 4.7) — «Личный кабинет ученика».
 * Сейчас на голых моках; когда появится API, mockStudentDashboard.ts
 * заменяется на хук с реальным запросом — типы (src/types/dashboard.ts)
 * и сами компоненты ниже не меняются.
 */
export function StudentHome() {
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
      userFullName={mockStudent.fullName}
      userRoleLabel={mockStudent.className}
    >
      <h2>Добрый день, {mockStudent.firstName}</h2>
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
