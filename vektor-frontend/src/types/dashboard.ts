/**
 * Типы фронтенда для «Личного кабинета ученика» (Экран 1 из ТЗ, п. 4.7).
 * Названия полей ориентированы на сущности из ТЗ (раздел 6.3: tests_360,
 * surveys, historical_scores), но это самостоятельные фронтенд-типы —
 * сопоставление с ответом сервера живёт в местах вызова (см. toPendingSurvey
 * в pages/student/StudentHome.tsx).
 */

export type SurveyStatus = 'not_started' | 'in_progress';

export interface PendingSurvey {
  id: string;
  /** Бейдж сверху карточки, например «Самооценка · 360 · июнь 2026» */
  badgeLabel: string;
  /** Заголовок карточки, например «Опрос о классе 10А» */
  title: string;
  totalQuestions: number;
  answeredQuestions: number;
  status: SurveyStatus;
}

export interface CompletedResult {
  id: string;
  testTitle: string;
  competenciesCount: number;
  openedDateLabel: string;
  averageScore: number;
}
