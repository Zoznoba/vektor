import { useApi } from '../../hooks/useApi';
import { formatPeriod } from '../../data/period';
import type { GroupDynamics } from '../../types/results';
import { DynamicsChart } from './DynamicsChart';
import type { GroupAnalyticsData } from '../../data/groupAnalytics';
import { RadarChart } from '../charts/RadarChart';
import { shortCompetencyName } from '../../data/competencyShortNames';
import './GroupProfile.css';

/** Критерий в профиле группы, приведённый к общему виду: у класса это
 *  `class_avg`, у кейса — `case_avg`, но рисуются они одинаково. */
export interface GroupProfileAxis {
  competency_id: number;
  code: string;
  name: string;
  value: number | null;
  school: number | null;
}

/** Строка «где группа отстаёт от школы»: delta всегда отрицательная. */
export interface SchoolGapRow {
  competency_id: number;
  name: string;
  delta: number;
  value: number | null;
  school: number | null;
}

/** Строка «где себя видят иначе, чем окружающие»: знак значим. */
export interface SelfGapRow {
  competency_id: number;
  name: string;
  gap: number;
  self_avg: number | null;
  others_avg: number | null;
}

/**
 * Средний профиль группы (класса или кейса) против школы.
 *
 * Один компонент на три экрана — диагностику класса у учителя, «Мои кейсы» и
 * аналитику класса у админа. Раньше каждый строил радар сам, и это была
 * ровно та же тройная копия, что и на бэкенде до сведения class/case в
 * `_group_profile`: три места, которые обязаны считать и подписывать
 * одинаково, но ничем не связаны.
 */
export function GroupProfileChart({ label, axes }: { label: string; axes: GroupProfileAxis[] }) {
  // Оси только там, где есть хоть одно значение: критерий, закрытый по
  // возрасту (профпробы до 9 класса), дал бы пустой луч и перекосил фигуру.
  const scored = axes.filter((a) => a.value !== null || a.school !== null);

  if (scored.length < 3) {
    // Радар — единственное представление профиля, поэтому у вырожденного
    // набора осей нужна явная строка, а не пустота.
    return <div className="app-main__sub">Критериев с баллом слишком мало для профиля</div>;
  }

  return (
    <RadarChart
      axes={scored.map((a) => shortCompetencyName(a.code, a.name))}
      axisTitles={scored.map((a) => a.name)}
      series={[
        { label, values: scored.map((a) => a.value), color: 'var(--blue)' },
        { label: 'Школа', values: scored.map((a) => a.school), color: '#a6a2a3', dashed: true },
      ]}
    />
  );
}

/**
 * «Где группа отстаёт от школы» — критерии с самой большой отрицательной
 * разницей со средним по школе за тот же период.
 *
 * Пришло на смену «зонам роста по охвату личных зон»: та метрика была
 * относительной (у каждого ученика ровно три личные зоны, независимо от
 * того, насколько плохи дела), а её счётчик «6 учеников» без знаменателя
 * читался как «шестеро провалились». Отставание от школы отвечает на
 * вопрос, ради которого экран и открывают: чем ЭТА группа отличается —
 * критерий, низкий у всей школы, не проблема класса.
 *
 * Пустой список — честный ответ «группа нигде заметно не отстаёт», а не
 * повод показать три случайных критерия.
 */
export function SchoolGapList({ rows, label }: { rows: SchoolGapRow[]; label: string }) {
  if (rows.length === 0) {
    return <div className="app-main__sub">Заметного отставания от школы нет</div>;
  }

  return (
    <>
      <div className="app-main__sub">Разница со средним по школе за тот же период</div>
      {rows.map((row) => (
        <div className="growth-zone" key={row.competency_id}>
          <div className="growth-zone__score growth-zone__score--behind">
            {row.delta.toFixed(1)}
          </div>
          <div className="growth-zone__name">{row.name}</div>
          <div className="growth-zone__count">
            {label} {row.value === null ? '—' : row.value.toFixed(1)} · школа{' '}
            {row.school === null ? '—' : row.school.toFixed(1)}
          </div>
        </div>
      ))}
    </>
  );
}

/**
 * «Где себя видят иначе, чем окружающие» — единственное место на экране
 * группы, где видно собственно 360°: средний балл и сравнение со школой
 * одинаково считались бы и по обычной оценке учителя.
 *
 * Знак сохраняем и подписываем словами: «себя выше» — повод присмотреться,
 * «себя ниже» — повод поддержать. Это два разных разговора с классом, и
 * сводить их к одной «величине расхождения» нельзя.
 */
export function SelfGapList({ rows }: { rows: SelfGapRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="app-main__sub">
        Самооценка и оценка окружающих заметно не расходятся
      </div>
    );
  }

  return (
    <>
      <div className="app-main__sub">Средняя самооценка против средней оценки окружающих</div>
      {rows.map((row) => (
        <div className="growth-zone" key={row.competency_id}>
          <div
            className={`growth-zone__score ${
              row.gap > 0 ? 'growth-zone__score--above' : 'growth-zone__score--behind'
            }`}
          >
            {row.gap > 0 ? '+' : ''}
            {row.gap.toFixed(1)}
          </div>
          <div className="growth-zone__name">
            {row.name}
            <span className="growth-zone__note">
              {row.gap > 0 ? 'себя выше' : 'себя ниже'}
            </span>
          </div>
          <div className="growth-zone__count">
            себя {row.self_avg === null ? '—' : row.self_avg.toFixed(1)} · окружающие{' '}
            {row.others_avg === null ? '—' : row.others_avg.toFixed(1)}
          </div>
        </div>
      ))}
    </>
  );
}


interface GroupAnalyticsProps {
  /** Подпись серии на радаре и в строках сравнения: «8-1» или «Кейс «…»». */
  label: string;
  averageLabel: string;
  /** «класс» / «кейс» — для заголовков разделов под радаром. */
  groupNoun: string;
  /** Обязана быть стабильной ссылкой (useCallback) — иначе useApi зациклится. */
  load: () => Promise<GroupAnalyticsData>;
  /** Что написать, когда завершённой диагностики по группе ещё не было. */
  emptyText: string;
  /** Динамика по критериям. Тоже стабильная ссылка. */
  loadDynamics: () => Promise<GroupDynamics>;
}

/**
 * Аналитика группы целиком: плитки, радар против школы и зоны роста.
 *
 * Один компонент на четыре места (класс и кейс у админа, «Мои кейсы» у
 * учителя, диагностика класса), потому что различий между классом и кейсом
 * ровно два — источник данных и подписи, — и оба стали параметрами. То же
 * решение, что на бэкенде: `_group_profile` с колонкой снапшота параметром.
 *
 * 404 здесь штатный: по группе могло не быть ни одной ЗАВЕРШЁННОЙ кампании
 * (по идущей баллы не отдаются вовсе). Отличаем его от настоящего сбоя по
 * status, а не по тексту ошибки.
 */
export function GroupAnalytics({
  label,
  averageLabel,
  groupNoun,
  load,
  emptyText,
  loadDynamics,
}: GroupAnalyticsProps) {
  const results = useApi(load);

  if (results.loading && !results.data) {
    return <div className="admin-empty">Загрузка…</div>;
  }

  if (results.error || !results.data) {
    return <div className="admin-empty">{results.status === 404 ? emptyText : results.error}</div>;
  }

  const data = results.data;

  return (
    <>
      {/* Явно про состав НА МОМЕНТ КАМПАНИИ: ниже на странице стоит вкладка
          «Ученики · N» с сегодняшним составом, и без этой оговорки два разных
          числа рядом читаются как ошибка (7-1 прошлого года — 11 человек в
          диагностике и 2 в классе сейчас). */}
      <div className="app-main__sub">
        {data.campaignTitle} · {formatPeriod(data.periodYear, data.periodMonth)} ·{' '}
        {data.studentsWithResults} учеников в диагностике (состав на момент кампании)
      </div>

      <div className="group-analytics__tiles">
        <div className="group-analytics__tile">
          <div className="group-analytics__value group-analytics__value--blue">
            {data.average === null ? '—' : data.average.toFixed(2)}
          </div>
          <div className="group-analytics__label">{averageLabel}</div>
        </div>
        <div className="group-analytics__tile">
          <div className="group-analytics__value">
            {data.schoolAverage === null ? '—' : data.schoolAverage.toFixed(2)}
          </div>
          <div className="group-analytics__label">Средний по школе за период</div>
        </div>
      </div>

      <GroupProfileChart label={label} axes={data.axes} />

      <GroupDynamicsSection load={loadDynamics} groupNoun={groupNoun} />

      <div className="group-analytics__zones-title">Где {groupNoun} отстаёт от школы</div>
      <SchoolGapList rows={data.schoolGaps} label={label} />

      <div className="group-analytics__zones-title">
        Где себя видят иначе, чем окружающие
      </div>
      <SelfGapList rows={data.selfGaps} />
    </>
  );
}


/**
 * «Как изменилось за год» — те же столбики «было/стало», что на странице
 * ученика, только по средним группы.
 *
 * Показывается ТОЛЬКО когда предыдущий период есть: у пятиклассников и у
 * первого года кружка его нет по построению, и пустой блок с заголовком
 * читался бы как «не загрузилось». Ошибку загрузки тоже не показываем —
 * это дополнение к профилю, а не его часть: профиль выше уже отрисован, и
 * красная строка под ним сбивала бы с толку.
 *
 * Подпись «сравниваются N из M» обязательна: в сравнение идут только те, у
 * кого есть оба периода, и у класса, куда кто-то пришёл в этом году, числа
 * разойдутся — молча показывать «динамику класса» по половине состава нельзя.
 */
export function GroupDynamicsSection({
  load,
  groupNoun,
}: {
  load: () => Promise<GroupDynamics>;
  groupNoun: string;
}) {
  const dynamics = useApi(load);
  const data = dynamics.data;

  if (!data || data.previous_campaign_id === null) return null;

  const scored = data.competencies.filter((c) => c.overall_avg !== null);
  if (scored.length === 0) return null;

  const previousLabel =
    data.previous_campaign_period_year !== null && data.previous_campaign_period_month !== null
      ? formatPeriod(data.previous_campaign_period_year, data.previous_campaign_period_month)
      : 'пред. период';

  return (
    <>
      <div className="group-analytics__zones-title">Как изменился {groupNoun} за год</div>
      <div className="app-main__sub">
        Сравниваются {data.students_compared} из {data.students_total} — те, у кого есть оба
        периода
      </div>
      <DynamicsChart
        competencies={scored}
        previousLabel={previousLabel}
        currentLabel={formatPeriod(data.campaign_period_year, data.campaign_period_month)}
      />
      {data.versions_differ && data.version_note && (
        <div className="app-main__sub">{data.version_note}</div>
      )}
    </>
  );
}
