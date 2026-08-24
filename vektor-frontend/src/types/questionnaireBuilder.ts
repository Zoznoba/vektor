/**
 * Типы, зеркалящие Pydantic-схемы конструктора анкеты
 * (modules/competencies/schemas.py, раздел «Конструктор анкеты»).
 */

export type QuestionnaireVersionStatus = 'draft' | 'published';

export interface QuestionnaireVersion {
  id: number;
  code: string;
  title: string;
  note: string | null;
  status: QuestionnaireVersionStatus;
  is_current: boolean;
  created_at: string;
}

export interface BuilderQuestion {
  id: number;
  text: string;
  order: number;
}

export interface BuilderCompetency {
  id: number;
  name: string;
  description: string | null;
  order: number;
  min_grade: number | null;
  max_grade: number | null;
  is_archived: boolean;
  is_draft: boolean;
  questions: BuilderQuestion[];
}

export interface BuilderOutcomeArea {
  id: number;
  name: string;
  order: number;
  is_archived: boolean;
  is_draft: boolean;
  competencies: BuilderCompetency[];
}

export interface QuestionnaireTree {
  version: QuestionnaireVersion;
  outcome_areas: BuilderOutcomeArea[];
}

export type MoveDirection = 'up' | 'down';
