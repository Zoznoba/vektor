/**
 * Типы фронтенда для «Личного кабинета ученика» (Экран 1 из ТЗ, п. 4.7).
 * Названия полей ориентированы на сущности из ТЗ (раздел 6.3: tests_360,
 * surveys, historical_scores), но это самостоятельные фронтенд-типы —
 * при подключении API их можно сопоставить с ответом сервера в одном месте
 * (см. data/mock.ts, который будет заменён на реальный fetch).
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

export interface StudentInfo {
  fullName: string;
  firstName: string;
  className: string;
  academicYear: string;
}
