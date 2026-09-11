import { useCallback, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { fetchSchoolResults } from '../../api/results';
import { formatPeriod } from '../../data/period';
import { withPlural } from '../../data/plural';
import type { SchoolCompetency, SchoolResults } from '../../types/results';
import { RadarChart } from '../charts/RadarChart';
import type { RadarAxisTone, RadarSeries } from '../charts/RadarChart';
import { shortCompetencyName } from '../../data/competencyShortNames';
import './SchoolAnalytics.css';

/** Сколько осей выделять с каждого края. Две, а не три: критериев всего 11,
 *  и при трёх выделенной оказывается половина круга — выделение перестаёт
 *  что-либо значить. */
const HIGHLIGHT_COUNT = 2;

/** Критерий, у которого есть балл за текущий период: только такие участвуют
 *  в ранжировании. */
type ScoredCompetency = SchoolCompetency & { avg: number };

/** Чем показан профиль школы: фигурой или числами. */
type ProfileView = 'chart' | 'table';

/**
 * Аналитика по школе целиком — блок сводки админа.
 *
 * Единица наблюдения — ПЕРИОД, а не кампания: диагностику заводят кампанией
 * на каждый класс, поэтому «школа за кампанию» вырождалась бы в один класс
 * (то же решение, что у сравнения группы со школой).
 *
 * Экран считает только отображение: выделение осей — это сортировка уже
 * посчитанных приростов, а не доменное правило. Всё, что требует правил
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
    () => current.competencies.filter((c): c is ScoredCompetency => c.avg !== null),
    [current.competencies],
  );
  // Выделяем ИЗМЕНЕНИЕ за год, а не уровень: «средний балл 3.2» сам по себе
  // ничего не говорит (шкала 1–5 и разные критерии живут в разных диапазонах),
  // а «за год выросло на 0.9» и «почти не сдвинулось» — это уже разговор с
  // завучем. Метрика ОДНА на оба конца: сверху самый большой прирост, снизу
  // самый маленький (он же отрицательный, если критерий просел).
  //
  // Прошлого периода нет (первый год школы) — падаем на уровень: «нуждается в
  // росте» тогда значит «ниже всех», и подпись под чартом это говорит прямо.
  const byGrowth = useMemo(() => {
    const withDelta = scored.filter((c) => c.delta !== null);
    if (withDelta.length >= HIGHLIGHT_COUNT * 2) {
      const sorted = [...withDelta].sort((a, b) => (b.delta as number) - (a.delta as number));
      return { rows: sorted, byDelta: true };
    }
    return { rows: [...scored].sort((a, b) => b.avg - a.avg), byDelta: false };
  }, [scored]);

  const strongest = byGrowth.rows.slice(0, HIGHLIGHT_COUNT);
  const weakest = byGrowth.rows.slice(-HIGHLIGHT_COUNT).reverse();

  const previousLabel =
    current.previous_period_year !== null && current.previous_period_month !== null
      ? formatPeriod(current.previous_period_year, current.previous_period_month)
      : null;
  const currentLabel = formatPeriod(current.period_year, current.period_month);

  // Чарт или таблица — два ВИДА одного и того же, поэтому переключатель, а
  // не отдельный сворачиваемый блок ниже: раньше таблица жила внизу страницы
  // и читалась как другие данные, хотя цифры в ней те же самые.
  const [view, setView] = useState<ProfileView>('chart');

  return (
    <>
      {/* Периоды — чипы, как переключатели классов у учителя и детей у
          родителя. Свои классы, а не .filter-chip со страниц админки: тянуть
          стили экрана в общий компонент значило бы связать их через CSS.

          Строки «Июнь 2026 · 136 учеников · 12 кампаний» над ними больше
          нет: период назван активным чипом, охват — строкой ниже, а сколько
          кампаний завели на период — техника проведения диагностики, она
          видна на экране «Диагностика». */}
      {data.periods.length > 1 && (
        <div className="school-analytics__head">
          <div className="school-periods" role="group" aria-label="Период диагностики">
            {[...data.periods].reverse().map((p) => {
              const active =
                p.period_year === current.period_year && p.period_month === current.period_month;
              return (
                <button
                  type="button"
                  key={`${p.period_year}-${p.period_month}`}
                  className={`school-period${active ? ' school-period--active' : ''}`}
                  aria-pressed={active}
                  onClick={() => onPeriodChange({ year: p.period_year, month: p.period_month })}
                >
                  {formatPeriod(p.period_year, p.period_month)}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Две строки вместо четырёх плиток: балл с приростом НА ОДНОЙ строке
          (прирост без балла рядом нечитаем — «+0.37» само по себе не число,
          а изменение), и одной строкой охват. Крупная цифра тут одна: на
          сводке эти числа — контекст к графикам ниже, а не содержание. */}
      <div className="school-stats">
        <div className="school-stats__score">
          <span className="school-stats__value">{current.average.toFixed(2)}</span>
          {current.core_average_delta !== null && (
            <span
              className={`school-stats__delta${
                current.core_average_delta > 0 ? ' school-stats__delta--up' : ''
              }${current.core_average_delta < 0 ? ' school-stats__delta--down' : ''}`}
            >
              {current.core_average_delta > 0 ? '+' : current.core_average_delta < 0 ? '−' : '±'}
              {Math.abs(current.core_average_delta).toFixed(2)}
              {previousLabel ? ` к «${previousLabel}»` : ' за год'}
            </span>
          )}
          <span className="school-stats__caption">средний балл школы</span>
        </div>

        <div className="school-stats__coverage">
          {withPlural(current.students_with_results, ['ученик', 'ученика', 'учеников'])} из{' '}
          {withPlural(current.classes.length, ['класса', 'классов', 'классов'])}
          {current.cases_with_results > 0 &&
            ` и ${withPlural(current.cases_with_results, ['кейса', 'кейсов', 'кейсов'])}`}
          {' — состав на момент кампании'}
        </div>
      </div>

      {/* Две колонки на одной линии: слева «кто», справа «что». Это два
          разреза одних и тех же данных, и смотрят их вместе — «класс просел»
          и «просел вот этот критерий» складываются в один вывод, только если
          видны разом. Узкий экран складывает их в столбик. */}
      <div className="school-analytics__grid">
        <section>
          <div className="school-analytics__title">Классы по среднему баллу</div>
          <ClassBars rows={current.classes} schoolAverage={current.average} />
        </section>

        <section>
          <div className="school-analytics__section-head">
            <div className="school-analytics__title">Профиль школы по критериям</div>
            <div className="school-switch" role="group" aria-label="Вид профиля">
              <button
                type="button"
                className={`school-switch__option${view === 'chart' ? ' school-switch__option--active' : ''}`}
                onClick={() => setView('chart')}
              >
                Чарт
              </button>
              <button
                type="button"
                className={`school-switch__option${view === 'table' ? ' school-switch__option--active' : ''}`}
                onClick={() => setView('table')}
              >
                Таблица
              </button>
            </div>
          </div>

          {view === 'chart' ? (
            <SchoolRadar
              competencies={current.competencies}
              currentLabel={currentLabel}
              previousLabel={previousLabel}
              strongest={strongest}
              weakest={weakest}
              byDelta={byGrowth.byDelta}
            />
          ) : (
            <CompetencyTable rows={current.competencies} previousLabel={previousLabel} />
          )}
        </section>
      </div>
    </>
  );
}

/**
 * Профиль школы «этот год против прошлого» — тот же радар, что у класса и
 * кейса (решение 7q: паутинка везде, где показывается профиль).
 *
 * Прошлый период рисуется пунктиром и серым, как «Школа» в профиле группы:
 * это фон, с которым сравнивают, а не вторая равноправная серия.
 *
 * Ось остаётся и там, где значение есть только у одной из серий (критерий
 * появился или закрылся между годами): выкинуть её значило бы спрятать
 * реальный критерий этого года. Отсутствующую точку RadarChart кладёт на
 * минимум шкалы, а в подсказке оси показывает «—», поэтому наведением видно,
 * что данных нет; сноску под графиком про это убрали — экран сводки читают
 * бегло, и абзац мелким текстом там только шумел.
 *
 * Выделение живёт НА ФИГУРЕ — точка на вершине и подпись оси в тот же цвет,
 * без списка снизу: список повторял те же критерии второй раз, и глазами
 * приходилось сопоставлять его с фигурой. Что значат цвета, говорит строка
 * легенды под чартом — одна, а не блок.
 */
function SchoolRadar({
  competencies,
  currentLabel,
  previousLabel,
  strongest,
  weakest,
  byDelta,
}: {
  competencies: SchoolCompetency[];
  currentLabel: string;
  previousLabel: string | null;
  strongest: ScoredCompetency[];
  weakest: ScoredCompetency[];
  /** Чем выделены оси: приростом за год или уровнем (первый год школы). */
  byDelta: boolean;
}) {
  const scored = competencies.filter((c) => c.avg !== null || c.previous_avg !== null);
  if (scored.length < 3) {
    return <div className="app-main__sub">Критериев с баллом слишком мало для профиля</div>;
  }

  const series: RadarSeries[] = [
    { label: currentLabel, values: scored.map((c) => c.avg), color: 'var(--blue)' },
  ];
  if (previousLabel) {
    series.push({
      label: previousLabel,
      values: scored.map((c) => c.previous_avg),
      color: '#a6a2a3',
      dashed: true,
    });
  }

  const strongIds = new Set(strongest.map((c) => c.competency_id));
  const weakIds = new Set(weakest.map((c) => c.competency_id));
  const axisTones: (RadarAxisTone | null)[] = scored.map((c) =>
    weakIds.has(c.competency_id) ? 'weak' : strongIds.has(c.competency_id) ? 'strong' : null,
  );

  return (
    <>
      <RadarChart
        axes={scored.map((c) => shortCompetencyName(c.code, c.name))}
        axisTitles={scored.map((c) => c.name)}
        axisTones={axisTones}
        series={series}
      />

      <div className="school-radar__legend">
        <span className="school-radar__legend-item">
          <span className="school-radar__key school-radar__key--strong" />
          {byDelta ? 'выросли сильнее всего' : 'выше всего'}
        </span>
        <span className="school-radar__legend-item">
          <span className="school-radar__key school-radar__key--weak" />
          {byDelta ? 'нуждаются в росте: прибавили меньше всех' : 'нуждаются в росте: ниже всего'}
        </span>
      </div>
    </>
  );
}

/** Как отсортированы классы. «По классу» — исходный порядок бэкенда
 *  (5-1, 5-2, 6-1…). */
type ClassSort = 'class' | 'average';

/**
 * Классы по среднему баллу — горизонтальные полосы.
 *
 * Полоса от НУЛЯ: длина здесь и есть значение, а обрезанная база превратила
 * бы разницу в 0.4 балла в двукратную.
 *
 * На каждой полосе стоит засечка среднего по школе — с ней видно не только
 * «кто выше кого», но и насколько класс отходит от школы; без неё полосы
 * сравнивались только друг с другом. Засечка повторяется в каждой строке, а
 * не рисуется одной линией поверх списка: строки одинаковой ширины, и
 * повторённые метки складываются в ту же вертикаль, зато вёрстка не зависит
 * от подгонки отступов под колонки.
 *
 * По умолчанию порядок — по возрастанию класса: чаще экран открывают, чтобы
 * найти КОНКРЕТНЫЙ класс, а в рейтинге он каждый период на новом месте.
 * Сортировка по баллу — по клику, и повторный клик её переворачивает: «кто
 * слабее всех» и «кто сильнее всех» задают одинаково часто.
 *
 * Строка ведёт на страницу класса: сводка отвечает «где просело», а
 * следующий вопрос всегда «а что там внутри».
 */
function ClassBars({
  rows,
  schoolAverage,
}: {
  rows: { class_id: number; class_label: string; students_with_results: number; average: number }[];
  schoolAverage: number;
}) {
  const [sort, setSort] = useState<ClassSort>('class');
  const [descending, setDescending] = useState(true);

  const sorted = useMemo(() => {
    if (sort === 'class') return rows;
    const byAverage = [...rows].sort((a, b) => a.average - b.average);
    return descending ? byAverage.reverse() : byAverage;
  }, [rows, sort, descending]);

  if (rows.length === 0) return <div className="app-main__sub">Классов с результатами нет</div>;

  const pick = (next: ClassSort) => {
    // Повторный клик по активной сортировке переворачивает её — отдельная
    // кнопка направления ради двух состояний была бы лишним элементом.
    if (next === sort && next === 'average') setDescending((prev) => !prev);
    setSort(next);
  };

  const best = Math.max(...rows.map((r) => r.average));

  return (
    <div className="school-classes">
      <div className="school-switch">
        <button
          type="button"
          className={`school-switch__option${
            sort === 'class' ? ' school-switch__option--active' : ''
          }`}
          onClick={() => pick('class')}
        >
          По классу
        </button>
        <button
          type="button"
          className={`school-switch__option${
            sort === 'average' ? ' school-switch__option--active' : ''
          }`}
          onClick={() => pick('average')}
        >
          По баллу {sort === 'average' && (descending ? '↓' : '↑')}
        </button>
      </div>

      {sorted.map((row) => {
        const delta = row.average - schoolAverage;
        return (
          <Link
            className="school-classes__row"
            key={row.class_id}
            to="/admin/classes"
            state={{ classId: row.class_id }}
            // Охват уехал в подсказку: в узкой колонке пятая цифра съедала
            // полосу, а «сколько учеников» спрашивают реже, чем «сколько
            // баллов».
            title={`${row.class_label}: ${row.students_with_results} учеников в диагностике — открыть класс`}
          >
            <div className="school-classes__label">{row.class_label}</div>
            <div className="school-classes__track">
              <div
                className={`school-classes__bar${
                  delta < 0 ? ' school-classes__bar--below' : ''
                }${row.average === best ? ' school-classes__bar--best' : ''}`}
                style={{ width: `${(row.average / 5) * 100}%` }}
              />
              <div
                className="school-classes__mark"
                style={{ left: `${(schoolAverage / 5) * 100}%` }}
              />
            </div>
            <div className="school-classes__value">{row.average.toFixed(2)}</div>
            <div
              className={`school-classes__delta${
                delta < 0 ? ' school-classes__delta--below' : ''
              }`}
            >
              {delta > 0 ? '+' : delta < 0 ? '−' : '±'}
              {Math.abs(delta).toFixed(2)}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

/** Колонка таблицы критериев: как её зовут и что из строки брать. */
interface TableColumn {
  key: string;
  title: string;
  /** Значение для сортировки. null — «нет данных», такие строки всегда внизу. */
  value: (row: SchoolCompetency) => number | string | null;
  /** Текст в ячейке. */
  render: (row: SchoolCompetency) => string;
}

const SCORE_CELL = (value: number | null) => (value === null ? '—' : value.toFixed(2));

/**
 * Табличный вид тех же чисел: у диаграмм читается направление, а точные
 * значения по слоям нужны, когда с ними идут разговаривать.
 *
 * Сортировка по любой колонке, три состояния по кругу: сначала «интересное
 * сверху» (у чисел — по убыванию, у названия — по алфавиту), потом наоборот,
 * потом обратно к порядку МЕТОДИКИ. Третье состояние нужно, потому что
 * исходный порядок не случайный: критерии идут внутри своих «ОР / навык», и
 * потерять эту группировку насовсем — потерять смысл списка.
 *
 * Пустые значения всегда внизу, в любом направлении: «—» это отсутствие
 * данных, а не самое маленькое число. Иначе критерий, которого не было в
 * прошлом году, возглавлял бы сортировку по приросту.
 */
function CompetencyTable({
  rows,
  previousLabel,
}: {
  rows: SchoolCompetency[];
  previousLabel: string | null;
}) {
  const [sort, setSort] = useState<{ key: string; descending: boolean } | null>(null);

  const columns: TableColumn[] = [
    { key: 'name', title: 'Критерий', value: (r) => r.name, render: (r) => r.name },
    { key: 'avg', title: 'Итог', value: (r) => r.avg, render: (r) => SCORE_CELL(r.avg) },
    {
      key: 'self',
      title: 'Самооценка',
      value: (r) => r.self_avg,
      render: (r) => SCORE_CELL(r.self_avg),
    },
    {
      key: 'others',
      title: 'Окружающие',
      value: (r) => r.others_avg,
      render: (r) => SCORE_CELL(r.others_avg),
    },
    {
      key: 'previous',
      title: previousLabel ?? 'Прошлый период',
      value: (r) => r.previous_avg,
      render: (r) => SCORE_CELL(r.previous_avg),
    },
    {
      key: 'delta',
      title: 'Прирост',
      value: (r) => r.delta,
      render: (r) => (r.delta === null ? '—' : `${r.delta > 0 ? '+' : ''}${r.delta.toFixed(2)}`),
    },
  ];

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column) return rows;

    return [...rows].sort((a, b) => {
      const left = column.value(a);
      const right = column.value(b);
      if (left === null || right === null) {
        // Оба пустые — оставляем как есть (сортировка стабильная), иначе
        // пустой всегда ниже, независимо от направления.
        if (left === right) return 0;
        return left === null ? 1 : -1;
      }
      const diff =
        typeof left === 'string' && typeof right === 'string'
          ? left.localeCompare(right, 'ru')
          : (left as number) - (right as number);
      return sort.descending ? -diff : diff;
    });
    // columns пересоздаются каждый рендер (в них замыкания на previousLabel),
    // поэтому в зависимостях их нет — от сортировки зависят только rows и sort.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sort]);

  const toggle = (column: TableColumn) => {
    setSort((prev) => {
      // Первый клик: у чисел сверху большие, у названия — алфавит. Второй —
      // наоборот. Третий — обратно к порядку методики.
      const numeric = column.key !== 'name';
      if (prev?.key !== column.key) return { key: column.key, descending: numeric };
      if (prev.descending === numeric) return { key: column.key, descending: !numeric };
      return null;
    });
  };

  return (
    <div className="school-table__scroll">
      <table className="admin-table school-table">
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sort?.key === column.key;
              return (
                <th key={column.key} aria-sort={active ? (sort.descending ? 'descending' : 'ascending') : 'none'}>
                  <button
                    type="button"
                    className={`school-table__sort${active ? ' school-table__sort--active' : ''}`}
                    onClick={() => toggle(column)}
                  >
                    {column.title}
                    <span className="school-table__arrow">
                      {active ? (sort.descending ? '↓' : '↑') : ''}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.competency_id}>
              {columns.map((column) => (
                <td key={column.key}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
