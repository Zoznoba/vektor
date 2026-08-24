import { apiRequest } from './client';
import type {
  BuilderCompetency,
  BuilderOutcomeArea,
  BuilderQuestion,
  MoveDirection,
  QuestionnaireTree,
  QuestionnaireVersion,
} from '../types/questionnaireBuilder';

export function fetchQuestionnaireVersions(): Promise<QuestionnaireVersion[]> {
  return apiRequest<QuestionnaireVersion[]>('/questionnaire-versions');
}

export function createDraftVersion(): Promise<QuestionnaireVersion> {
  return apiRequest<QuestionnaireVersion>('/questionnaire-versions/draft', { method: 'POST' });
}

export function fetchQuestionnaireTree(versionId: number): Promise<QuestionnaireTree> {
  return apiRequest<QuestionnaireTree>(`/questionnaire-versions/${versionId}/tree`);
}

export function publishVersion(versionId: number): Promise<QuestionnaireVersion> {
  return apiRequest<QuestionnaireVersion>(`/questionnaire-versions/${versionId}/publish`, {
    method: 'POST',
  });
}

export function discardDraft(versionId: number): Promise<void> {
  return apiRequest<void>(`/questionnaire-versions/${versionId}`, { method: 'DELETE' });
}

export function addOutcomeArea(versionId: number, name: string): Promise<BuilderOutcomeArea> {
  return apiRequest(`/questionnaire-versions/${versionId}/outcome-areas`, {
    method: 'POST',
    body: { name },
  });
}

export function updateOutcomeArea(areaId: number, name: string): Promise<BuilderOutcomeArea> {
  return apiRequest(`/outcome-areas/${areaId}`, { method: 'PATCH', body: { name } });
}

export function archiveOutcomeArea(
  areaId: number,
  isArchived: boolean,
): Promise<BuilderOutcomeArea> {
  return apiRequest(`/outcome-areas/${areaId}/archive`, {
    method: 'PATCH',
    body: { is_archived: isArchived },
  });
}

export function moveOutcomeArea(
  areaId: number,
  direction: MoveDirection,
): Promise<BuilderOutcomeArea> {
  return apiRequest(`/outcome-areas/${areaId}/move`, { method: 'PATCH', body: { direction } });
}

export interface CompetencyIn {
  name: string;
  description?: string | null;
  min_grade?: number | null;
  max_grade?: number | null;
}

export function addCompetency(
  versionId: number,
  areaId: number,
  data: CompetencyIn,
): Promise<BuilderCompetency> {
  return apiRequest(
    `/questionnaire-versions/${versionId}/outcome-areas/${areaId}/competencies`,
    { method: 'POST', body: data },
  );
}

export function updateCompetency(
  competencyId: number,
  data: CompetencyIn,
): Promise<BuilderCompetency> {
  return apiRequest(`/competencies/${competencyId}`, { method: 'PATCH', body: data });
}

export function archiveCompetency(
  competencyId: number,
  isArchived: boolean,
): Promise<BuilderCompetency> {
  return apiRequest(`/competencies/${competencyId}/archive`, {
    method: 'PATCH',
    body: { is_archived: isArchived },
  });
}

export function moveCompetency(
  competencyId: number,
  direction: MoveDirection,
): Promise<BuilderCompetency> {
  return apiRequest(`/competencies/${competencyId}/move`, {
    method: 'PATCH',
    body: { direction },
  });
}

export function addQuestion(
  versionId: number,
  competencyId: number,
  text: string,
): Promise<BuilderQuestion> {
  return apiRequest(`/questionnaire-versions/${versionId}/competencies/${competencyId}/questions`, {
    method: 'POST',
    body: { text },
  });
}

export function updateQuestion(questionId: number, text: string): Promise<BuilderQuestion> {
  return apiRequest(`/questions/${questionId}`, { method: 'PATCH', body: { text } });
}

export function deleteQuestion(questionId: number): Promise<void> {
  return apiRequest<void>(`/questions/${questionId}`, { method: 'DELETE' });
}

export function moveQuestion(
  questionId: number,
  direction: MoveDirection,
): Promise<BuilderQuestion> {
  return apiRequest(`/questions/${questionId}/move`, { method: 'PATCH', body: { direction } });
}
