import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Panel } from '../../components/ui/Panel';
import { PeriodSelect } from '../../components/ui/PeriodSelect';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/icons/Icon';
import {
  GroupDynamicsSection,
  GroupProfileChart,
  SchoolGapList,
  SelfGapList,
} from '../../components/dashboard/GroupProfile';
import { useApi } from '../../hooks/useApi';
import {
  fetchClassCampaigns,
  fetchClassResults,
  fetchClassRoster,
  fetchGroupDynamics,
} from '../../api/results';
import { fetchMyAssessments } from '../../api/assessments';
import { defaultCampaignId } from '../../data/period';
import type { ClassRosterRow } from '../../types/results';
import type { AssessmentListItem } from '../../types/assessment';

const SELF_STATUS_LABEL: Record<string, string> = {
  not_started: 'Не начата',
  in_progress: 'В процессе',
  completed: 'Завершена',
};

/** «Не выдана» — отдельное состояние: анкеты нет, а не «есть и не начата». */
function selfStatusLabel(status: ClassRosterRow['self_status']): string {
  return status === null ? 'Не выдана' : SELF_STATUS_LABEL[status];
}

function formatDelta(delta: number | null): string {
  if (delta === null) return '—';
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`;
}

type FilterKey = 'all' | 'not_started' | 'growth';

type SortKey = 'name' | 'self' | 'collected' | 'score' | 'delta';
type SortDir = 'asc' | 'desc';

const SELF_STATUS_ORDER: Record<string, number> = {
  none: 0,
  not_started: 1,
  in_progress: 2,
  completed: 3,
};

function RosterTh({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
}: {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const active = sortKey === col;
  return (
    <th
      className={`roster__th-sort ${active ? 'roster__th-sort--active' : ''}`.trim()}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={() => onSort(col)}
    >
      {label}
      <span className="roster__sort-caret">
        {active ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
      </span>
    </th>
  );
}

interface ClassDiagnosticsProps {
  classId: number;
  /**
   * Чем смотрящий занят в этом классе («архитектура», «кл. руководитель»).
   * Раньше это висело тегом на КАЖДОМ чипе класса и у предметника с
   * дюжиной классов повторялось дюжину раз — здесь оно нужно один раз, про
   * тот класс, который открыт. Необязательная: у админа роли в классе нет.
   */
  roleNote?: string | null;
}

/**
 * Метрики, состав и профиль одного класса.
 *
 * Отдельный компонент, а не кусок страницы: так запросы уходят только когда
 * classId уже известен. Раньше страница «пропускала» запрос через
 * Promise.reject, пока грузился список классов, — и эта искусственная ошибка
 * переживала успешную загрузку, из-за чего экран писал «диагностики нет»
 * поверх нормальных данных.
 */
export function ClassDiagnostics({ classId, roleNote }: ClassDiagnosticsProps) {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<FilterKey>('all');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  // Явный выбор в переключателе периодов. Пока его нет — умолчание из
  // defaultCampaignId: самая свежая кампания НЫНЕШНЕГО состава, ЛЮБОГО
  // статуса (этот экран — мониторинг, ради идущей диагностики его и
  // открывают). Сбрасывать при смене класса не нужно: родитель пересоздаёт
  // блок по key={classId}, и состояние уезжает вместе со старым классом.
  const [pickedCampaignId, setPickedCampaignId] = useState<number | undefined>(undefined);

  // useApi требует стабильную ссылку — иначе effect уходит в цикл запросов.
  const loadCampaigns = useCallback(() => fetchClassCampaigns(classId), [classId]);
  const campaigns = useApi(loadCampaigns);
  const campaignId = pickedCampaignId ?? defaultCampaignId(campaigns.data ?? []);
  const selectedCampaign = campaigns.data?.find((c) => c.campaign_id === campaignId);

  // Пока период не выбран (список ещё грузится или своей диагностики у
  // состава не было), запрашивать нечего: «класс» без периода не определяет
  // группу людей.
  const loadRoster = useCallback(() => fetchClassRoster(classId, campaignId), [classId, campaignId]);
  const roster = useApi(loadRoster, { skip: campaignId === undefined });

  // Профиль и динамика идут за ТЕМ ЖЕ периодом, что и состав выше: иначе
  // таблица показывала бы одних детей, а радар под ней — других.
  //
  // По идущей кампании баллов нет вовсе (бэкенд отвечает 409): пока она не
  // закрыта, профиль не запрашиваем и пишем об этом словами. Раньше в этом
  // случае рисовался профиль, сшитый из прошлых диагностик каждого ученика, —
  // и он молча выдавал прошлогодние числа за результат идущей.
  const scoresReady = selectedCampaign?.status === 'closed';
  const loadResults = useCallback(
    () => fetchClassResults(classId, campaignId as number),
    [classId, campaignId],
  );
  const loadDynamics = useCallback(
    () => fetchGroupDynamics('class', classId, campaignId),
    [classId, campaignId],
  );
  const results = useApi(loadResults, { skip: !scoresReady });
  // Свои анкеты нужны, чтобы кнопка «Оценить» вела в конкретную анкету.
  // Отдельным полем в ростере это не отдаём: ростер — про класс, а «моя
  // анкета про ученика» зависит от того, кто смотрит, и админ получил бы
  // пустоту в каждой строке.
  const myAssessments = useApi(fetchMyAssessments);

  const assessmentBySubject = useMemo(() => {
    const map = new Map<number, AssessmentListItem>();
    const campaignId = roster.data?.campaign_id;
    for (const item of myAssessments.data ?? []) {
      // Только текущая кампания класса и только чужие анкеты: самооценка
      // учителя (пилот на педагогах) к строке ученика отношения не имеет.
      if (item.campaign_id !== campaignId || item.is_self) continue;
      map.set(item.subject.id, item);
    }
    return map;
  }, [myAssessments.data, roster.data?.campaign_id]);

  const students = roster.data?.students ?? [];

  const filtered = useMemo(() => {
    if (filter === 'not_started') {
      // «Не начали» — про самооценку ученика: она и есть то, что от него
      // требуется. Не выданную анкету тоже считаем — она точно не начата.
      return students.filter((s) => s.self_status === 'not_started' || s.self_status === null);
    }
    if (filter === 'growth') return students.filter((s) => s.growth_zone_count > 0);
    return students;
  }, [students, filter]);

  // Сортировка поверх фильтра. Пустые баллы/динамика всегда в конце, в обе
  // стороны: у половины класса ещё нет прошлого периода, и гонять их наверх
  // при развороте бессмысленно.
  const sorted = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1;
    const rows = [...filtered];
    rows.sort((a, b) => {
      const byName = a.subject.full_name.localeCompare(b.subject.full_name, 'ru');
      if (sortKey === 'name') return dir * byName;
      if (sortKey === 'self') {
        const av = SELF_STATUS_ORDER[a.self_status ?? 'none'];
        const bv = SELF_STATUS_ORDER[b.self_status ?? 'none'];
        return av === bv ? byName : dir * (av - bv);
      }
      if (sortKey === 'collected') {
        const av = a.assessments_total ? a.assessments_completed / a.assessments_total : 0;
        const bv = b.assessments_total ? b.assessments_completed / b.assessments_total : 0;
        return av === bv ? byName : dir * (av - bv);
      }
      const av = sortKey === 'score' ? a.overall_avg : a.delta;
      const bv = sortKey === 'score' ? b.overall_avg : b.delta;
      if (av === null && bv === null) return byName;
      if (av === null) return 1;
      if (bv === null) return -1;
      return av === bv ? byName : dir * (av - bv);
    });
    return rows;
  }, [filtered, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir(key === 'name' ? 'asc' : 'desc');
    }
  };

  const counts = useMemo(
    () => ({
      all: students.length,
      not_started: students.filter((s) => s.self_status === 'not_started' || s.self_status === null)
        .length,
      growth: students.filter((s) => s.growth_zone_count > 0).length,
    }),
    [students],
  );

  if (campaigns.loading || roster.loading) {
    return (
      <Panel>
        <div className="app-main__sub">Загрузка…</div>
      </Panel>
    );
  }

  // 404 здесь — штатное «диагностики по классу ещё не было». Остальные ошибки
  // (403 нет доступа, 500 и т.п.) показываем текстом, а не прячем за этим же
  // приветливым пустым стейтом — иначе учитель видит «нет диагностики» вместо
  // «нет доступа» и не понимает, что дело в привязке к классу.
  if (roster.error && roster.status !== 404) {
    return (
      <Panel>
        <div className="form-error">{roster.error}</div>
      </Panel>
    );
  }

  // Переключатель периодов рисуется и над пустым экраном тоже: по умолчанию
  // открывается только кампания НЫНЕШНЕЙ когорты, а её у нового набора ещё
  // нет — при этом архив прошлых лет по этой строке класса существует, и без
  // переключателя до него было бы не добраться вовсе.
  const periodSwitcher = (
    <PeriodSelect
      campaigns={campaigns.data ?? []}
      value={campaignId}
      onChange={setPickedCampaignId}
    />
  );

  const metrics = roster.data;

  const filters: { key: FilterKey; label: string }[] = [
    { key: 'all', label: `Все · ${counts.all}` },
    { key: 'not_started', label: `Не начали · ${counts.not_started}` },
    { key: 'growth', label: `Есть зоны роста · ${counts.growth}` },
  ];

  return (
    <>
      {/* Переключатель — НАД метриками: он меняет и их, и радар ниже, а стоя
          под ними читался бы как фильтр одной только таблицы состава. */}
      {periodSwitcher}

      {/* Состав и метрики есть только тогда, когда по классу выдана кампания.
          Профиль ниже от этого не зависит: он считается по нынешним ученикам
          и их последним диагностикам, даже если общей кампании у класса нет
          ни одной. */}
      {metrics ? (
        <>
        <div className="teacher-metrics">
          <div className="teacher-metric">
            <div className="teacher-metric__value">{metrics.students_count}</div>
            <div className="teacher-metric__label">Учеников в классе</div>
          </div>
          <div className="teacher-metric">
            <div className="teacher-metric__value teacher-metric__value--blue">
              {Math.round(metrics.coverage_percent)}%
            </div>
            <div className="teacher-metric__label">
              Анкет заполнено · {metrics.assessments_completed} из {metrics.assessments_total}
            </div>
          </div>
          <div className="teacher-metric">
            <div className="teacher-metric__value">{metrics.class_average?.toFixed(2) ?? '—'}</div>
            <div className="teacher-metric__label">Средний балл класса</div>
          </div>
          <div className="teacher-metric">
            <div className="teacher-metric__value teacher-metric__value--sage">
              {formatDelta(metrics.average_delta)}
            </div>
            <div className="teacher-metric__label">Динамика за год</div>
          </div>
        </div>

        <Panel
          title={[`Состав ${metrics.class_label}`, roleNote, metrics.campaign_title]
            .filter(Boolean)
            .join(' · ')}
        >
          {metrics.campaign_status === 'closed' && (
            /* Кампания закрыта — значит состав тут ИСТОРИЧЕСКИЙ: снапшот на её
               момент, а не сегодняшний список класса. Оговорка обязательна:
               школа переиспользует классы из года в год, поэтому у закрытой
               диагностики 8-1 и у вкладки состава класса сегодня — разные дети,
               и два разных числа рядом читаются как ошибка. Та же оговорка, что
               в GroupProfile. */
            <div className="app-main__sub">
              Диагностика завершена — состав на момент кампании
            </div>
          )}

          <div className="roster-filters">
            {filters.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`roster-filter ${
                  filter === item.key ? 'roster-filter--active' : ''
                }`.trim()}
                onClick={() => setFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="roster-scroll">
            <table className="roster">
              <thead>
                <tr>
                  <RosterTh label="Ученик" col="name" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <RosterTh label="Самооценка" col="self" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <RosterTh label="Собрано" col="collected" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <RosterTh label="Балл" col="score" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <RosterTh label="Дин." col="delta" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <th />
                </tr>
              </thead>
              <tbody>
                {sorted.map((row) => {
                  const myAssessment = assessmentBySubject.get(row.subject.id);
                  return (
                    <tr
                      key={row.subject.id}
                      className="roster__row"
                      onClick={() => navigate(`/teacher/students/${row.subject.id}`)}
                    >
                      <td className="roster__name">{row.subject.full_name}</td>
                      <td>
                        <span
                          className={`roster__status roster__status--${row.self_status ?? 'none'}`}
                        >
                          {selfStatusLabel(row.self_status)}
                        </span>
                      </td>
                      <td className="roster__muted">
                        {row.assessments_completed} из {row.assessments_total}
                      </td>
                      <td className="roster__score">
                        {row.overall_avg === null ? '—' : row.overall_avg.toFixed(2)}
                      </td>
                      <td
                        className={`roster__delta ${
                          row.delta !== null && row.delta > 0 ? 'roster__delta--up' : ''
                        }`.trim()}
                      >
                        {formatDelta(row.delta)}
                      </td>
                      <td className="roster__action" onClick={(e) => e.stopPropagation()}>
                        {/* «Оценить» только там, где анкета этого учителя про
                            ученика реально существует и не завершена. Кнопкой
                            со словом, а не значком, она осталась намеренно:
                            строка с ней — это «здесь ещё есть работа», и по
                            этому признаку таблицу просматривают глазами.
                            «Профиль» же был одинаков во ВСЕХ строках и читался
                            дюжиной белых коробок — он ушёл в клик по строке,
                            от него остался значок-стрелка. */}
                        {myAssessment && myAssessment.status !== 'completed' && (
                          <Button
                            className="btn-sm"
                            onClick={() => navigate(`/assessments/${myAssessment.id}`)}
                          >
                            {myAssessment.status === 'not_started' ? 'Оценить' : 'Продолжить'}
                          </Button>
                        )}
                        {/* Настоящая кнопка, а не декоративная иконка: клик по
                            строке мышью удобен, но с клавиатуры недоступен. */}
                        <button
                          type="button"
                          className="roster__open"
                          aria-label={`Профиль: ${row.subject.full_name}`}
                          title="Профиль ученика"
                          onClick={() => navigate(`/teacher/students/${row.subject.id}`)}
                        >
                          <Icon name="arrowRight" size={16} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {filtered.length === 0 && (
            <div className="app-main__sub">По этому фильтру учеников нет</div>
          )}
        </Panel>
        </>
      ) : (
        <Panel>
          <div className="app-main__sub">
            {roster.status === 404 || campaignId === undefined
              ? 'Диагностика по нынешнему составу класса ещё не выдавалась — выберите период выше, чтобы посмотреть архив прошлых наборов.'
              : (roster.error ?? 'Загрузка…')}
          </div>
        </Panel>
      )}

      <Panel title="Средний профиль класса">
        {!scoresReady ? (
          /* Баллы существуют только у закрытой кампании: пока диагностика
             идёт, часть анкет не заполнена, и средние по ним — не результат
             класса, а промежуточный срез сбора. */
          <div className="app-main__sub">
            {campaignId === undefined
              ? 'Профиль появится, когда по классу пройдёт диагностика.'
              : 'Диагностика ещё идёт — профиль появится после её завершения. Прошлые периоды доступны в списке выше.'}
          </div>
        ) : results.loading ? (
          <div className="app-main__sub">Загрузка…</div>
        ) : results.data ? (
          <>
            <div className="app-main__sub">{results.data.class_label} против школы</div>
            <GroupProfileChart
              label={results.data.class_label}
              axes={results.data.competencies.map((c) => ({
                competency_id: c.competency_id,
                code: c.code,
                name: c.name,
                value: c.class_avg,
                school: c.school_avg,
              }))}
            />
          </>
        ) : (
          <div className="app-main__sub">Профиль пока не посчитан</div>
        )}
      </Panel>

      {results.data && (
        <Panel title="На что смотреть в классе">
          <div className="group-analytics__zones-title">Где класс отстаёт от школы</div>
          <SchoolGapList
            rows={results.data.school_gaps.map((gap) => ({
              competency_id: gap.competency_id,
              name: gap.name,
              delta: gap.delta,
              value: gap.class_avg,
              school: gap.school_avg,
            }))}
            label={results.data.class_label}
          />

          <div className="group-analytics__zones-title">Где себя видят иначе, чем окружающие</div>
          <SelfGapList rows={results.data.self_gaps} />

          <GroupDynamicsSection load={loadDynamics} groupNoun="класс" />
        </Panel>
      )}
    </>
  );
}
