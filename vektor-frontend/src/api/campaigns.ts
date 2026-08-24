import { apiRequest } from './client';
import type { Campaign, CampaignCoverage, CampaignListItem, GenerateResult } from '../types/campaign';

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
 * teacherIdsByClass — какие учителя класса участвуют: {classId: [teacherId]}.
 * Класса нет в объекте → участвуют ВСЕ его учителя (прежнее поведение);
 * пустой массив → учительских анкет по классу не будет.
 */
export function generateAssessments(
  campaignId: number,
  classIds: number[],
  teacherIdsByClass: Record<number, number[]>,
): Promise<GenerateResult> {
  return apiRequest<GenerateResult>(`/campaigns/${campaignId}/generate`, {
    method: 'POST',
    body: { class_ids: classIds, teacher_ids_by_class: teacherIdsByClass },
  });
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
