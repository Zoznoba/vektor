import { apiRequest } from './client';
import type { SubjectResults } from '../types/results';

/**
 * Результаты субъекта по критериям.
 *
 * campaignId необязателен: без него бэкенд берёт самую свежую кампанию, где у
 * субъекта есть анкеты (по `period`, а не по id — архив прошлого года
 * импортируется позже текущего и получает больший id). Дашборду это и нужно:
 * он показывает «мои результаты», не зная про кампании.
 *
 * Если результатов нет вообще — 404, а не пустой ответ.
 */
export function fetchSubjectResults(
  subjectId: number,
  campaignId?: number,
): Promise<SubjectResults> {
  const query = campaignId !== undefined ? `?campaign_id=${campaignId}` : '';
  return apiRequest<SubjectResults>(`/results/${subjectId}${query}`);
}
