import type { CompletedResult, PendingSurvey, StudentInfo } from '../types/dashboard';

/**
 * Заглушка данных. Когда появится API (см. ТЗ, раздел 6 — REST/JSON),
 * этот файл удаляется, а компоненты страницы получают те же типы
 * через хук вида useStudentDashboard(), который дёргает реальный эндпоинт.
 */

export const mockStudent: StudentInfo = {
  fullName: 'Полина Иванова',
  firstName: 'Полина',
  className: '10А класс',
  academicYear: '2025/2026 учебный год',
};

export const mockPendingSurveys: PendingSurvey[] = [
  {
    id: 'survey-self-360-2026-06',
    badgeLabel: 'Самооценка · 360 · июнь 2026',
    title: 'Самооценка',
    totalQuestions: 33,
    answeredQuestions: 0,
    status: 'not_started',
  },
  {
    id: 'survey-peer-10a-2026-06',
    badgeLabel: 'Оценить одноклассников',
    title: 'Опрос о классе 10А',
    totalQuestions: 33,
    answeredQuestions: 12,
    status: 'in_progress',
  },
];

export const mockCompletedResults: CompletedResult[] = [
  {
    id: 'result-360-2026-03',
    testTitle: '360-диагностика · март 2026',
    competenciesCount: 8,
    openedDateLabel: 'открыто 14 марта',
    averageScore: 2.4,
  },
];
