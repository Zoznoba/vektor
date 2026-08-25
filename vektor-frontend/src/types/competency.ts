/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/competencies/schemas.py).
 * Контракт: CompetencyOut, OutcomeAreaOut, QuestionOut.
 */

export interface CompetencyQuestion {
  id: number;
  text: string;
  order: number;
}

export interface OutcomeArea {
  id: number;
  code: string;
  name: string;
  order: number;
}

export interface Competency {
  id: number;
  code: string;
  name: string;
  description: string | null;
  order: number;
  min_grade: number | null;
  max_grade: number | null;
  outcome_area: OutcomeArea;
  questions: CompetencyQuestion[];
}
