import { apiRequest } from './client';
import type {
  Campaign,
  CampaignCoverage,
  CampaignDeleteResult,
  CampaignListItem,
  GenerateResult,
} from '../types/campaign';

export function fetchCampaigns(): Promise<CampaignListItem[]> {
  return apiRequest<CampaignListItem[]>('/campaigns');
}

export interface CreateCampaignIn {
  title: string;
  period_year: number;
  period_month: number;
}

export function createCampaign(data: CreateCampaignIn): Promise<Campaign> {
  return apiRequest<Campaign>('/campaigns', { method: 'POST', body: data });
}

/**
 * Кампания собирается из классов и/или кейсов — нужен хотя бы один источник,
 * пустой запрос бэкенд отклоняет (422).
 *
 * teacherIdsByClass / teacherIdsByCase — какие учителя участвуют:
 * {classId: [teacherId]}. Класса (кейса) нет в объекте → участвуют ВСЕ его
 * учителя (прежнее поведение); пустой массив → учительских анкет по нему не
 * будет вовсе.
 */
export interface GenerateSources {
  classIds?: number[];
  teacherIdsByClass?: Record<number, number[]>;
  caseIds?: number[];
  teacherIdsByCase?: Record<number, number[]>;
}

export function generateAssessments(
  campaignId: number,
  sources: GenerateSources,
): Promise<GenerateResult> {
  return apiRequest<GenerateResult>(`/campaigns/${campaignId}/generate`, {
    method: 'POST',
    body: {
      class_ids: sources.classIds ?? [],
      teacher_ids_by_class: sources.teacherIdsByClass ?? {},
      case_ids: sources.caseIds ?? [],
      teacher_ids_by_case: sources.teacherIdsByCase ?? {},
    },
  });
}

/**
 * Удаляет кампанию вместе со всеми анкетами и ответами. Необратимо —
 * вызывать только после подтверждения пользователем.
 */
export function deleteCampaign(campaignId: number): Promise<CampaignDeleteResult> {
  return apiRequest<CampaignDeleteResult>(`/campaigns/${campaignId}`, { method: 'DELETE' });
}

export function closeCampaign(campaignId: number): Promise<Campaign> {
  return apiRequest<Campaign>(`/campaigns/${campaignId}/close`, { method: 'PATCH' });
}

export function reopenCampaign(campaignId: number): Promise<Campaign> {
  return apiRequest<Campaign>(`/campaigns/${campaignId}/reopen`, { method: 'PATCH' });
}

export function fetchCampaignCoverage(campaignId: number): Promise<CampaignCoverage> {
  return apiRequest<CampaignCoverage>(`/results/campaigns/${campaignId}/coverage`);
}
