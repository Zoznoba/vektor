import { apiRequest } from './client';
import type { Campaign, CampaignCoverage, CampaignListItem, GenerateResult } from '../types/campaign';

export function fetchCampaigns(): Promise<CampaignListItem[]> {
  return apiRequest<CampaignListItem[]>('/campaigns');
}

export interface CreateCampaignIn {
  title: string;
  period: string;
  opens_at?: string | null;
  closes_at?: string | null;
}

export function createCampaign(data: CreateCampaignIn): Promise<Campaign> {
  return apiRequest<Campaign>('/campaigns', { method: 'POST', body: data });
}

export function generateAssessments(
  campaignId: number,
  classIds: number[],
  includePeers: boolean,
): Promise<GenerateResult> {
  return apiRequest<GenerateResult>(`/campaigns/${campaignId}/generate`, {
    method: 'POST',
    body: { class_ids: classIds, include_peers: includePeers },
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
