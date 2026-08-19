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
  campaign_period: string;
  campaign_closes_at: string | null;
  subject: User;
  is_self: boolean;
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
