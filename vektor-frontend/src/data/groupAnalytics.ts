/**
 * Приведение ответов «профиль класса» и «профиль кейса» к общему виду.
 *
 * Бэкенд отдаёт одни и те же числа под разными именами полей (`class_avg` /
 * `case_avg`) — разные они там осознанно, чтобы по ответу было видно, чей это
 * профиль. Фронту же рисовать их одинаково, поэтому конвертеры живут в одном
 * месте, а не расползаются по экранам.
 *
 * Отдельный модуль от компонента: файл с компонентами не должен экспортировать
 * ещё и функции — иначе ломается Fast Refresh (react-refresh/only-export-components).
 */
import type { GroupProfileAxis, SchoolGapRow, SelfGapRow } from '../components/dashboard/GroupProfile';
import type { CaseResults, ClassResults } from '../types/results';

/** Профиль группы, приведённый к общему виду: класс и кейс отдают одни и те
 *  же числа под разными именами полей (`class_avg` / `case_avg`). */
export interface GroupAnalyticsData {
  campaignTitle: string;
  periodYear: number;
  periodMonth: number;
  studentsWithResults: number;
  average: number | null;
  schoolAverage: number | null;
  axes: GroupProfileAxis[];
  schoolGaps: SchoolGapRow[];
  selfGaps: SelfGapRow[];
}

export function classResultsToAnalytics(data: ClassResults): GroupAnalyticsData {
  return {
    campaignTitle: data.campaign_title,
    periodYear: data.campaign_period_year,
    periodMonth: data.campaign_period_month,
    studentsWithResults: data.students_with_results,
    average: data.class_average,
    schoolAverage: data.school_average,
    axes: data.competencies.map((c) => ({
      competency_id: c.competency_id,
      code: c.code,
      name: c.name,
      value: c.class_avg,
      school: c.school_avg,
    })),
    schoolGaps: data.school_gaps.map((g) => ({
      competency_id: g.competency_id,
      name: g.name,
      delta: g.delta,
      value: g.class_avg,
      school: g.school_avg,
    })),
    selfGaps: data.self_gaps,
  };
}

export function caseResultsToAnalytics(data: CaseResults): GroupAnalyticsData {
  return {
    campaignTitle: data.campaign_title,
    periodYear: data.campaign_period_year,
    periodMonth: data.campaign_period_month,
    studentsWithResults: data.students_with_results,
    average: data.case_average,
    schoolAverage: data.school_average,
    axes: data.competencies.map((c) => ({
      competency_id: c.competency_id,
      code: c.code,
      name: c.name,
      value: c.case_avg,
      school: c.school_avg,
    })),
    schoolGaps: data.school_gaps.map((g) => ({
      competency_id: g.competency_id,
      name: g.name,
      delta: g.delta,
      value: g.case_avg,
      school: g.school_avg,
    })),
    selfGaps: data.self_gaps,
  };
}
