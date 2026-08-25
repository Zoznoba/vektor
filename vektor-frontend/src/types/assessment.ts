/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/assessments/schemas.py).
 * Контракт: AssessmentListItemOut, AssessmentDetailOut, SubmitResult.
 */

import type { User } from './auth';

export type AssessmentStatus = 'not_started' | 'in_progress' | 'completed';
export type RaterRole = 'self' | 'peer' | 'teacher' | 'parent';

export interface AssessmentListItem {
  id: number;
  campaign_id: number;
  campaign_title: string;
  campaign_period_year: number;
  campaign_period_month: number;
  subject: User;
  is_self: boolean;
  /**
   * Роль респондента по отношению к субъекту, зафиксированная при генерации
   * анкеты. Именно по ней собирается подпись карточки: учитель оценивает
   * ученика, а не одноклассника. Роль залогиненного пользователя тут не
   * годится — учитель может оценивать и как родитель своего ребёнка.
   */
  rater_role: RaterRole;
  status: AssessmentStatus;
  answered_questions: number;
  total_questions: number;
}

export interface AssessmentQuestion {
  id: number;
  competency_id: number;
  text: string;
  order: number;
  is_conditional: boolean;
  value: number | null;

  /**
   * Критерий и глава приходят вместе с вопросом — группировка НЕ ходит за
   * ними в GET /competencies. Тот отдаёт только действующую методику, а
   * опубликованная редакция может содержать вопросы критерия,
   * заархивированного позже: по справочнику такой вопрос терялся, и анкета
   * не могла завершиться.
   */
  competency_name: string;
  competency_order: number;
  outcome_area_id: number;
  outcome_area_name: string;
  outcome_area_order: number;
}

export interface AssessmentDetail {
  id: number;
  campaign_id: number;
  campaign_title: string;
  subject: User;
  rater_role: RaterRole;
  questions: AssessmentQuestion[];
}

export interface SubmitResult {
  assessment_id: number;
  status: AssessmentStatus;
  answered_questions: number;
  total_questions: number;
}
