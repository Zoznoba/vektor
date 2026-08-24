/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/assessments/schemas.py,
 * modules/results/schemas.py — часть про покрытие).
 */

export type CampaignStatus = 'draft' | 'active' | 'closed';

export interface Campaign {
  id: number;
  title: string;
  /** Период — год + месяц числами. Название месяца собирает formatPeriod. */
  period_year: number;
  period_month: number;
  status: CampaignStatus;
  created_at: string;
}

export interface CampaignListItem extends Campaign {
  /** Агрегат по всей кампании (все классы вместе) — не путать с coverage по классам. */
  total_assessments: number;
  completed_assessments: number;
}

export interface GenerateResult {
  created: number;
  campaign: Campaign;
}

export interface ClassCoverageRow {
  /** null — анкеты без снапшота класса (субъект вне класса, пилот на учителях). */
  class_id: number | null;
  class_label: string | null;
  total: number;
  completed: number;
  percent: number;
}

/** Итог удаления кампании — сколько анкет и ответов ушло вместе с ней. */
export interface CampaignDeleteResult {
  campaign_id: number;
  assessments_deleted: number;
  answers_deleted: number;
}

export interface CampaignCoverage {
  campaign_id: number;
  campaign_title: string;
  campaign_period_year: number;
  campaign_period_month: number;
  total: number;
  completed: number;
  percent: number;
  classes: ClassCoverageRow[];
}
