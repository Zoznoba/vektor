/**
 * Типы, зеркалящие Pydantic-схемы бэкенда (modules/results/schemas.py).
 *
 * Единица разреза — КРИТЕРИЙ методики (их 11, по 3 вопроса в каждом). На бэке
 * сущность исторически называется competency, поэтому имена полей такие же —
 * переименовывать контракт ради терминологии не стали.
 *
 * Все *_avg приходят в шкале 1–5 и могут быть null: слой либо никем не
 * заполнен, либо скрыт правилом анонимности одноклассников (порог — 3 разных
 * человека ПО КАЖДОМУ критерию). null в peer_avg при peer_rater_count > 0 —
 * это не «нет данных», а «данные есть, но показывать нельзя».
 */

export interface CompetencyScore {
  competency_id: number;
  code: string;
  name: string;

  self_avg: number | null;
  peer_avg: number | null;
  teacher_avg: number | null;
  parent_avg: number | null;

  /** Среднее всех, кроме самооценки — вторая сторона разрыва. */
  others_avg: number | null;
  overall_avg: number | null;
  /** self_avg − others_avg. Положительный → себя оценивает выше окружающих. */
  gap: number | null;

  peer_rater_count: number;
  peer_scores_disclosed: boolean;
}

export interface GrowthZone {
  competency_id: number;
  code: string;
  name: string;
  overall_avg: number;
}

export interface SubjectResults {
  subject: { id: number; full_name: string };
  campaign_id: number;
  /** Уцелел ли слой одноклассников хоть где-то — под баннер «данных мало». */
  any_peer_scores_disclosed: boolean;
  overall_average: number | null;
  competencies: CompetencyScore[];
  growth_zones: GrowthZone[];
}
