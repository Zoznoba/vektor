/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/assessments/schemas.py,
 * modules/results/schemas.py — часть про покрытие).
 */

import type { AssessmentStatus } from './assessment';
import type { User } from './auth';

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

/** Один оценивающий внутри слоя — кто и заполнил ли анкету. */
export interface RaterStatus {
  id: number;
  full_name: string;
  status: AssessmentStatus;
}

/**
 * Один слой раторов про ученика. Пара чисел, а не «оценили/нет»: родителей
 * бывает двое, учителей 2–4, и «1 из 2» — не то же самое, что готово.
 * total === 0 — слой не выдавали вовсе.
 *
 * raters — тот же слой поимённо, приходит вместе со счётчиками: «1 из 2»
 * бесполезно, если непонятно, кому напоминать. Незаполнившие идут первыми
 * (порядок задаёт бэкенд).
 */
export interface LayerCoverage {
  total: number;
  completed: number;
  raters: RaterStatus[];
}

export interface CampaignStudentRow {
  subject: User;
  /** null — самооценку не сгенерировали (не то же, что not_started). */
  self_status: AssessmentStatus | null;
  parents: LayerCoverage;
  teachers: LayerCoverage;
  /** Слой убран из UI генерации (7o), но в прошлых кампаниях данные есть. */
  peers: LayerCoverage;
}

/**
 * Строка покрытия — класс ИЛИ кейс (кампания собирается из обоих, Этап 8).
 * Группировка по основанию выдачи: у анкеты кружка снапшот класса тоже
 * проставлен, но считается она в строке кейса — иначе диагностика кружка
 * растворялась бы в классах его участников. Анкета попадает ровно в одну
 * строку, поэтому сумма строк равна общему числу анкет.
 */
export interface CoverageGroup {
  /** Класс и кейс нумеруются независимо — что за строка, говорит kind. */
  kind: 'class' | 'case' | 'none';
  /** null — анкеты без снапшота класса (субъект вне класса, пилот на учителях). */
  class_id: number | null;
  class_label: string | null;
  case_id: number | null;
  case_name: string | null;
  total: number;
  completed: number;
  percent: number;
  /** Детализация той же строки по ученикам — приходит вместе с покрытием. */
  students: CampaignStudentRow[];
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
  groups: CoverageGroup[];
}
