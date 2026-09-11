import { apiRequest } from './client';
import type {
  CampaignRef,
  CaseResults,
  GroupDynamics,
  ClassResults,
  ClassRoster,
  SchoolResults,
  SubjectDynamics,
  SubjectResults,
} from '../types/results';

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

/**
 * Средний профиль класса, сравнение со школой и зоны роста класса.
 * Доступно админу и учителю ЭТОГО класса — остальным 403.
 *
 * campaignId ОБЯЗАТЕЛЕН: строки классов школа переиспользует из года в год,
 * поэтому «класс» без периода не определяет группу людей. Период выбирает
 * экран — список даёт fetchClassCampaigns, значение по умолчанию считает
 * defaultCampaignId (data/period).
 */
export function fetchClassResults(classId: number, campaignId: number): Promise<ClassResults> {
  return apiRequest<ClassResults>(`/results/class/${classId}?campaign_id=${campaignId}`);
}

/**
 * Динамика итогового балла и баллов по критериям относительно предыдущего
 * периода (сравнение только по общему ядру критериев — см. types/results.ts).
 * previous_campaign_id === null — предыдущего периода нет, это не ошибка.
 */
export function fetchSubjectDynamics(
  subjectId: number,
  campaignId?: number,
): Promise<SubjectDynamics> {
  const query = campaignId !== undefined ? `?campaign_id=${campaignId}` : '';
  return apiRequest<SubjectDynamics>(`/results/${subjectId}/dynamics${query}`);
}

/** Состав класса с прогрессом диагностики: строка на ученика + метрики шапки. */
export function fetchClassRoster(classId: number, campaignId?: number): Promise<ClassRoster> {
  const query = campaignId !== undefined ? `?campaign_id=${campaignId}` : '';
  return apiRequest<ClassRoster>(`/results/class/${classId}/roster${query}`);
}

/**
 * Периоды диагностики класса — под переключатель на экране класса.
 *
 * Список шире, чем «кампании этой строки класса»: в него входят и те, где
 * участвовали нынешние ученики под прежним ярлыком (сегодняшний 8-1 год назад
 * был 7-1). Без второй половины учитель не добрался бы до истории своего же
 * класса — см. list_campaigns_for_class на бэке.
 */
export function fetchClassCampaigns(classId: number): Promise<CampaignRef[]> {
  return apiRequest<CampaignRef[]>(`/results/class/${classId}/campaigns`);
}

/**
 * Средний профиль кейса, сравнение со школой и зоны роста группы.
 * Доступно админу и руководителю ЭТОГО кейса — остальным 403.
 * Без campaignId бэкенд берёт последнюю завершённую кампанию кейса; если
 * кейс ни в одну кампанию не попадал — 404, и это штатное «диагностики по
 * кейсу ещё не было», а не сбой.
 */
export function fetchCaseResults(caseId: number, campaignId?: number): Promise<CaseResults> {
  const query = campaignId !== undefined ? `?campaign_id=${campaignId}` : '';
  return apiRequest<CaseResults>(`/results/case/${caseId}${query}`);
}

/**
 * Динамика группы по критериям: текущий период против предыдущего.
 * `kind` выбирает эндпоинт — у класса и кейса они разные, а схема ответа одна.
 * Права те же, что у профиля группы. Нет ни одной завершённой кампании — 404.
 */
export function fetchGroupDynamics(
  kind: 'class' | 'case',
  groupId: number,
  campaignId?: number,
): Promise<GroupDynamics> {
  // У класса период обязателен (см. fetchClassResults), у кейса — нет: кружок
  // живёт со своим именем и составом, и «последняя кампания кейса» — это он
  // же и есть. Поэтому параметр остаётся опциональным на уровне подписи, а
  // обязательность класса держит вызывающая сторона.
  const query = campaignId !== undefined ? `?campaign_id=${campaignId}` : '';
  return apiRequest<GroupDynamics>(`/results/${kind}/${groupId}/dynamics${query}`);
}

/**
 * Аналитика по школе целиком: профиль за период + ряд по годам. Только админ.
 *
 * Период необязателен — без него бэкенд берёт последний период с
 * результатами. Пустая школа отдаёт `periods: []` и `current: null`, а не
 * 404: для новой школы это штатное состояние.
 */
export function fetchSchoolResults(period?: {
  year: number;
  month: number;
}): Promise<SchoolResults> {
  const query = period ? `?period_year=${period.year}&period_month=${period.month}` : '';
  return apiRequest<SchoolResults>(`/results/school${query}`);
}
