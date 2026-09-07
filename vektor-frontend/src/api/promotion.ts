import { apiRequest } from './client';

/**
 * Ежегодный перевод классов на класс вперёд (backend: modules/classes,
 * роуты /classes/promotion/*). Прошлую диагностику перевод не трогает —
 * она хранится в снапшотах анкет, а тут двигается только текущее членство.
 */

/** Один переход: один или несколько исходных классов → один целевой. */
export interface PromotionTransition {
  target_grade: number;
  target_section: string;
  target_label: string;
  /** null → целевого класса ещё нет, он будет создан. */
  target_class_id: number | null;
  source_class_ids: number[];
  source_labels: string[];
  moving_count: number;
  already_in_target_count: number;
  /** >1 источника или целевой класс уже с учениками (9-1 + 9-2 → 10). */
  merge: boolean;
}

export interface PromotionGraduating {
  class_id: number;
  class_label: string;
  student_count: number;
}

export interface PromotionPlan {
  academic_year: string;
  already_ran: boolean;
  transitions: PromotionTransition[];
  graduating: PromotionGraduating[];
  warnings: string[];
  total_moving: number;
  total_graduating: number;
  classes_to_create: number;
}

export interface PromotionRun {
  id: number;
  academic_year: string;
  ran_at: string;
  summary: { moved: number; graduated: number; classes_created: number };
  undone_at: string | null;
  /** false, если после перевода уже создана кампания (или он уже отменён). */
  can_undo: boolean;
}

/** Сухой прогон: план перевода, в БД ничего не меняет. */
export function previewPromotion(
  sectionOverrides: Record<number, string> = {},
): Promise<PromotionPlan> {
  return apiRequest<PromotionPlan>('/classes/promotion/preview', {
    method: 'POST',
    body: { section_overrides: sectionOverrides },
  });
}

export function applyPromotion(params: {
  confirmAcademicYear: string;
  sectionOverrides?: Record<number, string>;
  /** id исходных классов, чей состав учителей перенести в новый целевой класс. */
  carryTeachersFor?: number[];
}): Promise<PromotionRun> {
  return apiRequest<PromotionRun>('/classes/promotion/apply', {
    method: 'POST',
    body: {
      confirm_academic_year: params.confirmAcademicYear,
      section_overrides: params.sectionOverrides ?? {},
      carry_teachers_for: params.carryTeachersFor ?? [],
    },
  });
}

/** Активный перевод за текущий учебный год, либо null. */
export function fetchCurrentPromotion(): Promise<PromotionRun | null> {
  return apiRequest<PromotionRun | null>('/classes/promotion/current');
}

export function undoPromotion(runId: number): Promise<PromotionRun> {
  return apiRequest<PromotionRun>(`/classes/promotion/${runId}/undo`, { method: 'POST' });
}
