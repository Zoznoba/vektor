import { useCallback, useMemo, useState } from 'react';
import { useApi } from '../../hooks/useApi';
import { fetchSchoolResults } from '../../api/results';
import { formatPeriod } from '../../data/period';
import type { SchoolCompetency, SchoolResults } from '../../types/results';
import { TrendChart } from '../charts/TrendChart';
import { DynamicsChart } from './DynamicsChart';
import { Collapsible } from '../ui/Collapsible';
// Плитки и строки «критерий · балл» — те же, что у профиля группы: это одни и
// те же элементы интерфейса, и второй набор классов под них разошёлся бы с
// первым при первой же правке.
import './GroupProfile.css';
import './SchoolAnalytics.css';

/** Сколько критериев показывать в «сильных сторонах» и «зонах роста». */
const HIGHLIGHT_COUNT = 3;

/**
 * Аналитика по школе целиком — блок сводки админа.
 *
 * Единица наблюдения — ПЕРИОД, а не кампания: диагностику заводят кампанией
 * на каждый класс, поэтому «школа за кампанию» вырождалась бы в один класс
 * (то же решение, что у сравнения группы со школой).
 *
 * Экран считает только отображение: ранжирование критериев — это сортировка
 * уже посчитанных средних, а не доменное правило. Всё, что требует правил
 * (анонимность, вес ученика, общее ядро критериев), посчитано на бэкенде
 * один раз.
 */
export function SchoolAnalytics() {
  // null — «последний период», его выбирает бэкенд: на первом заходе фронт
  // ещё не знает, какие периоды вообще есть.
  const [period, setPeriod] = useState<{ year: number; month: number } | null>(null);
  const load = useCallback(() => fetchSchoolResults(period ?? undefined), [period]);
  const school = useApi(load);

  if (school.loading && !school.data) return <div className="admin-empty">Загрузка…</div>;
  if (school.error || !school.data) {
    return <div className="admin-empty">{school.error ?? 'Не удалось загрузить статистику'}</div>;
  }

  const data = school.data;
  if (!data.current || data.periods.length === 0) {
    return (
      <div className="admin-empty">
        Завершённых диагностик пока нет — статистика появится, когда первая кампания будет закрыта
      </div>
    );
  }

  return <SchoolAnalyticsBody data={data} onPeriodChange={setPeriod} />;
}

function SchoolAnalyticsBody({
  data,
  onPeriodChange,
}: {
  data: SchoolResults;
  onPeriodChange: (period: { year: number; month: number }) => void;
}) {
  const current = data.current!;
  const scored = useMemo(
    () => current.competencies.filter((c): c is SchoolCompetency & { avg: number } => c.avg !== null),
    [current.competencies],
  );
  // Ранжирование — обычная сортировка по уже посчитанному среднему. Порог
  // значимости здесь не нужен: это не «отставание от школы», а просто «выше
  // всех» и «ниже всех» внутри одного набора.
  const ranked = useMemo(() => [...scored].sort((a, b) => b.avg - a.avg), [scored]);
  const strongest = ranked.slice(0, HIGHLIGHT_COUNT);
  const weakest = ranked.slice(-HIGHLIGHT_COUNT).reverse();

  const previousLabel =
    current.previous_period_year !== null && current.previous_period_month !== null
      ? formatPeriod(current.previous_period_year, current.previous_period_month)
      : null;
  const currentLabel = formatPeriod(current.period_year, current.period_month);

  const trendPoints = data.periods.map((p) => ({
    label: formatPeriod(p.period_year, p.period_month),
    // На график идёт core_average — итог по общему ядру критериев. Если ядра
    // нет вовсе (единственный период), берём итог периода: точка одна, и
    // сравнивать её всё равно не с чем.
    value: p.core_average ?? p.average,
    note: `${p.students_with_results} учеников в диагностике`,
    active: p.period_year === current.period_year && p.period_month === current.period_month,
  }));

  const [tableOpen, setTableOpen] = useState(false);

  return (
    <>
      <div className="school-analytics__head">
        <div className="app-main__sub">
          {currentLabel} · {current.students_with_results} учеников в диагностике ·{' '}
          {current.campaigns_count} кампаний · состав на момент кампании
        </div>
        {data.periods.length > 1 && (
          <select
            className="school-analytics__period"
            value={`${current.period_year}-${current.period_month}`}
            onChange={(e) => {
              const [year, month] = e.target.value.split('-').map(Number);
              onPeriodChange({ year, month });
            }}
          >
            {[...data.periods].reverse().map((p) => (
              <option key={`${p.period_year}-${p.period_month}`} value={`${p.period_year}-${p.period_month}`}>
                {formatPeriod(p.period_year, p.period_month)}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="group-analytics__tiles">
        <div className="group-analytics__tile">
          <div className="group-analytics__value group-analytics__value--blue">
            {current.average.toFixed(2)}
          </div>
          <div className="group-analytics__label">Средний балл школы</div>
        </div>
        <div className="group-analytics__tile">
          <div className="group-analytics__value">
            {current.core_average_delta === null
              ? '—'
              : `${current.core_average_delta > 0 ? '+' : ''}${current.core_average_delta.toFixed(2)}`}
          </div>
          <div className="group-analytics__label">
            {previousLabel ? `Динамика к «${previousLabel}»` : 'Динамика за год'}
          </div>
        </div>
        <div className="group-analytics__tile">
          <div className="group-analytics__value">{current.students_with_results}</div>
          <div className="group-analytics__label">Учеников в диагностике</div>
        </div>
        <div className="group-analytics__tile">
          <div className="group-analytics__value">{current.classes.length}</div>
          <div className="group-analytics__label">Классов с результатами</div>
        </div>
      </div>

      <div className="group-analytics__zones-title">Динамика по годам</div>
      <div className="app-main__sub">
        Средний балл школы по общему ядру критериев ({data.core_competencies.length} из{' '}
        {current.competencies.length}) — только по тем, что мерили во всех периодах
      </div>
      <TrendChart points={trendPoints} />

      <div className="school-analytics__columns">
        <div>
          <div className="group-analytics__zones-title">Сильнее всего</div>
          <HighlightList rows={strongest} tone="above" />
        </div>
        <div>
          <div className="group-analytics__zones-title">Слабее всего</div>
          <HighlightList rows={weakest} tone="behind" />
        </div>
      </div>

      {previousLabel && (
        <>
          <div className="group-analytics__zones-title">Как изменилась школа за год</div>
          <div className="app-main__sub">
            Критерий без второго столбика мерили только в этом периоде — сравнивать не с чем
          </div>
          <DynamicsChart
            competencies={current.competencies.map((c) => ({
              competency_id: c.competency_id,
              code: c.code,
              name: c.name,
              overall_avg: c.avg,
              previous_avg: c.previous_avg,
              delta: c.delta,
              in_core: c.delta !== null,
            }))}
            previousLabel={previousLabel}
            currentLabel={currentLabel}
          />
        </>
      )}

      <div className="group-analytics__zones-title">Классы по среднему баллу</div>
      <ClassBars rows={current.classes} schoolAverage={current.average} />

      <Collapsible
        title="Все критерии школы"
        hint="Балл, самооценка, оценка окружающих и прирост к прошлому периоду"
        open={tableOpen}
        onToggle={() => setTableOpen((open) => !open)}
      >
        <CompetencyTable rows={current.competencies} previousLabel={previousLabel} />
      </Collapsible>
    </>
  );
}

/** Верх и низ рейтинга критериев — та же строка, что у зон роста группы. */
function HighlightList({
  rows,
  tone,
}: {
  rows: (SchoolCompetency & { avg: number })[];
  tone: 'above' | 'behind';
}) {
  if (rows.length === 0) return <div className="app-main__sub">Данных пока нет</div>;

  return (
    <>
      {rows.map((row) => (
        <div className="growth-zone" key={row.competency_id}>
          <div className={`growth-zone__score growth-zone__score--${tone}`}>
            {row.avg.toFixed(1)}
          </div>
          <div className="growth-zone__name">{row.name}</div>
          <div className="growth-zone__count">
            {row.delta === null
              ? 'новый критерий'
              : `${row.delta > 0 ? '+' : ''}${row.delta.toFixed(1)} за год`}
          </div>
        </div>
      ))}
    </>
  );
}

/**
 * Классы по среднему баллу — горизонтальные полосы.
 *
 * Полоса от НУЛЯ, в отличие от линии динамики: длина здесь и есть значение,
 * а обрезанная база превратила бы разницу в 0.4 балла в двукратную. Порядок —
 * по возрастанию класса (5-1, 5-2, 6-1…), а не по баллу: это состав школы, а
 * не турнирная таблица, и искать в нём нужно свой класс.
 */
function ClassBars({
  rows,
  schoolAverage,
}: {
  rows: { class_id: number; class_label: string; students_with_results: number; average: number }[];
  schoolAverage: number;
}) {
  if (rows.length === 0) return <div className="app-main__sub">Классов с результатами нет</div>;

  return (
    <div className="school-classes">
      {rows.map((row) => (
        <div className="school-classes__row" key={row.class_id}>
          <div className="school-classes__label">{row.class_label}</div>
          <div className="school-classes__track">
            <div
              className={`school-classes__bar${
                row.average < schoolAverage ? ' school-classes__bar--below' : ''
              }`}
              style={{ width: `${(row.average / 5) * 100}%` }}
            />
          </div>
          <div className="school-classes__value">{row.average.toFixed(2)}</div>
          <div className="school-classes__count">{row.students_with_results} чел.</div>
        </div>
      ))}
      <div className="app-main__sub">
        Серым — классы ниже среднего по школе ({schoolAverage.toFixed(2)})
      </div>
    </div>
  );
}

/** Табличный вид тех же чисел: у диаграмм читается направление, а точные
 *  значения по слоям нужны, когда с ними идут разговаривать. */
function CompetencyTable({
  rows,
  previousLabel,
}: {
  rows: SchoolCompetency[];
  previousLabel: string | null;
}) {
  const cell = (value: number | null) => (value === null ? '—' : value.toFixed(2));

  return (
    <div className="school-table__scroll">
      <table className="admin-table school-table">
        <thead>
          <tr>
            <th>Критерий</th>
            <th>Итог</th>
            <th>Самооценка</th>
            <th>Окружающие</th>
            <th>{previousLabel ?? 'Прошлый период'}</th>
            <th>Прирост</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.competency_id}>
              <td>{row.name}</td>
              <td>{cell(row.avg)}</td>
              <td>{cell(row.self_avg)}</td>
              <td>{cell(row.others_avg)}</td>
              <td>{cell(row.previous_avg)}</td>
              <td>
                {row.delta === null
                  ? '—'
                  : `${row.delta > 0 ? '+' : ''}${row.delta.toFixed(2)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
