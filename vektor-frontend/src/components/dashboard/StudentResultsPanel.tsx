import { useCallback } from 'react';
import { Panel } from '../ui/Panel';
import { Avatar } from '../ui/Avatar';
import { CompetencyDetailsTable } from './CompetencyDetailsTable';
import { RadarChart } from '../charts/RadarChart';
import { DynamicsChart } from './DynamicsChart';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { fetchSubjectResults, fetchSubjectDynamics } from '../../api/results';
import './StudentResultsPanel.css';
import { formatPeriod } from '../../data/period';
import { shortCompetencyName } from '../../data/competencyShortNames';

interface StudentResultsPanelProps {
  subjectId: number;
  /** «Мои результаты» на дашборде ученика, ФИО — на экране учителя/админа. */
  title?: string;
}

function formatDelta(delta: number | null): string {
  if (delta === null) return '—';
  return `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`;
}

/** Среднее непустых `gap` по критериям — общий «разрыв самооценки» тайлом. */
function averageGap(gaps: (number | null)[]): number | null {
  const known = gaps.filter((g): g is number => g !== null);
  if (known.length === 0) return null;
  return known.reduce((sum, g) => sum + g, 0) / known.length;
}

/**
 * Панель «Мои результаты».
 *
 * Отдельный компонент, а не кусок StudentHome: так хук загрузки вызывается
 * только когда subjectId уже известен, без non-null assertion на user внутри
 * зависимостей useCallback.
 */
export function StudentResultsPanel({
  subjectId,
  title = 'Мои результаты',
}: StudentResultsPanelProps) {
  const { user } = useAuth();
  // useApi требует стабильную ссылку — иначе effect уходит в цикл запросов.
  const loadResults = useCallback(() => fetchSubjectResults(subjectId), [subjectId]);
  const loadDynamics = useCallback(() => fetchSubjectDynamics(subjectId), [subjectId]);
  const results = useApi(loadResults);
  const dynamics = useApi(loadDynamics);

  // Шапку с именем/почтой ученика показываем только тому, кто смотрит НЕ на
  // себя (админ/учитель/родитель) — на своём дашборде ученик и так знает,
  // кто он, а «Мои результаты» + повтор своего имени читались бы как шум.
  const viewingOther = results.data && user && user.id !== results.data.subject.id;

  // Критерии без итогового балла не рисуем: у восьмиклассника это блок
  // профпроб (он открывается с 9 класса), и строка с прочерками читалась бы
  // как «низкий результат», а не «ещё не измеряется».
  const scored = (results.data?.competencies ?? []).filter((c) => c.overall_avg !== null);
  const gap = averageGap((results.data?.competencies ?? []).map((c) => c.gap));

  const dynamicsScored = (dynamics.data?.competencies ?? []).filter(
    (c) => c.overall_avg !== null,
  );

  return (
    <Panel title={title}>
      {results.loading ? (
        <div className="app-main__sub">Загрузка…</div>
      ) : results.error ? (
        /* 404 здесь — штатная ситуация «результатов ещё нет», а не сбой:
           у ученика может не быть ни одной кампании с анкетами. */
        <div className="app-main__sub">Результатов пока нет</div>
      ) : results.data ? (
        <>
          {viewingOther && (
            <div className="results-subject">
              <Avatar fullName={results.data.subject.full_name} className="results-subject__avatar" />
              <div className="results-subject__main">
                <div className="results-subject__name">{results.data.subject.full_name}</div>
                <div className="results-subject__email">{results.data.subject.email}</div>
              </div>
            </div>
          )}

          <div className="results-tiles">
            <div className="results-tile">
              <div className="results-tile__value">
                {results.data.overall_average === null
                  ? '—'
                  : results.data.overall_average.toFixed(2)}
              </div>
              <div className="results-tile__label">
                Средний балл по {scored.length} критериям
              </div>
            </div>
            <div className="results-tile">
              <div
                className={`results-tile__value ${
                  dynamics.data && dynamics.data.core_average_delta !== null
                    ? dynamics.data.core_average_delta >= 0
                      ? 'results-tile__value--up'
                      : 'results-tile__value--down'
                    : ''
                }`}
              >
                {dynamics.data ? formatDelta(dynamics.data.core_average_delta) : '—'}
              </div>
              <div className="results-tile__label">Динамика за год</div>
            </div>
            <div className="results-tile">
              <div className="results-tile__value">{gap === null ? '—' : gap.toFixed(2)}</div>
              <div className="results-tile__label">Разрыв самооценки</div>
            </div>
          </div>

          {scored.length >= 3 && (
            /* Радар вместо пары полос на критерий: заказчику он читается как
               единая форма профиля, а расхождение самооценки и окружающих
               видно тем же зазором между контурами. Меньше трёх осей радар
               не образует — там остаётся таблица «Детали по компетенциям». */
            <RadarChart
              axes={scored.map((c) => shortCompetencyName(c.code, c.name))}
              axisTitles={scored.map((c) => c.name)}
              series={[
                {
                  label: 'самооценка',
                  values: scored.map((c) => c.self_avg),
                  color: 'var(--blue)',
                },
                {
                  label: 'окружающие',
                  values: scored.map((c) => c.others_avg),
                  color: 'var(--sage)',
                },
              ]}
            />
          )}

          {results.data.growth_zones.length > 0 && (
            <div className="results-zones">
              <div className="results-section__title">Зоны роста</div>
              {results.data.growth_zones.map((zone) => (
                <div className="results-zones__item" key={zone.competency_id}>
                  <span>{zone.name}</span>
                  <span className="results-zones__score">{zone.overall_avg.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}

          {dynamics.data && dynamics.data.previous_campaign_id !== null && dynamicsScored.length > 0 && (
            <div className="results-dynamics">
              <div className="results-section__title">Динамика по годам</div>
              <DynamicsChart
                competencies={dynamicsScored}
                previousLabel={
                  dynamics.data.previous_campaign_period_year !== null &&
                  dynamics.data.previous_campaign_period_month !== null
                    ? formatPeriod(
                        dynamics.data.previous_campaign_period_year,
                        dynamics.data.previous_campaign_period_month,
                      )
                    : 'пред. период'
                }
                currentLabel={formatPeriod(
                  dynamics.data.campaign_period_year,
                  dynamics.data.campaign_period_month,
                )}
              />
              {dynamics.data.versions_differ && dynamics.data.version_note && (
                <div className="app-main__sub results-note">{dynamics.data.version_note}</div>
              )}
            </div>
          )}

          {scored.length > 0 && (
            <div className="results-dynamics">
              <div className="results-section__title">Детали по компетенциям</div>
              <CompetencyDetailsTable competencies={scored} />
            </div>
          )}
        </>
      ) : null}
    </Panel>
  );
}
