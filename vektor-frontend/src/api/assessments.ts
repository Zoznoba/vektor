import { apiRequest } from './client';
import type { AssessmentDetail, AssessmentListItem, SubmitResult } from '../types/assessment';

export function fetchMyAssessments(campaignId?: number): Promise<AssessmentListItem[]> {
  const query = campaignId !== undefined ? `?campaign_id=${campaignId}` : '';
  return apiRequest<AssessmentListItem[]>(`/assessments${query}`);
}

export function fetchAssessment(assessmentId: number): Promise<AssessmentDetail> {
  return apiRequest<AssessmentDetail>(`/assessments/${assessmentId}`);
}

export interface AnswerIn {
  question_id: number;
  value: number;
}

export function submitAnswers(assessmentId: number, answers: AnswerIn[]): Promise<SubmitResult> {
  return apiRequest<SubmitResult>(`/assessments/${assessmentId}/answers`, {
    method: 'POST',
    body: { answers },
  });
}
