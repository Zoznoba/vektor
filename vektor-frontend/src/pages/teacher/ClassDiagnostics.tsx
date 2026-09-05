import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import {
  GroupDynamicsSection,
  GroupProfileChart,
  SchoolGapList,
  SelfGapList,
} from '../../components/dashboard/GroupProfile';
import { useApi } from '../../hooks/useApi';
import { fetchClassResults, fetchClassRoster, fetchGroupDynamics } from '../../api/results';
import { fetchMyAssessments } from '../../api/assessments';
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

interface ClassDiagnosticsProps {
  classId: number;
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
export function ClassDiagnostics({ classId }: ClassDiagnosticsProps) {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<FilterKey>('all');

  // useApi требует стабильную ссылку — иначе effect уходит в цикл запросов.
  const loadRoster = useCallback(() => fetchClassRoster(classId), [classId]);
  const loadResults = useCallback(() => fetchClassResults(classId), [classId]);
  const loadDynamics = useCallback(() => fetchGroupDynamics('class', classId), [classId]);
  const roster = useApi(loadRoster);
  const results = useApi(loadResults);
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

  const counts = useMemo(
    () => ({
      all: students.length,
      not_started: students.filter((s) => s.self_status === 'not_started' || s.self_status === null)
        .length,
      growth: students.filter((s) => s.growth_zone_count > 0).length,
    }),
    [students],
  );

  if (roster.loading) {
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

  if (roster.error || !roster.data) {
    return (
      <Panel>
        <div className="app-main__sub">По этому классу ещё нет диагностики</div>
      </Panel>
    );
  }

  const metrics = roster.data;

  const filters: { key: FilterKey; label: string }[] = [
    { key: 'all', label: `Все · ${counts.all}` },
    { key: 'not_started', label: `Не начали · ${counts.not_started}` },
    { key: 'growth', label: `Есть зоны роста · ${counts.growth}` },
  ];

  return (
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

      <Panel title={`Состав ${metrics.class_label} · ${metrics.campaign_title}`}>
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
                <th>Ученик</th>
                <th>Самооценка</th>
                <th>Собрано</th>
                <th>Балл</th>
                <th>Дин.</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => {
                const myAssessment = assessmentBySubject.get(row.subject.id);
                return (
                  <tr key={row.subject.id}>
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
                    <td className="roster__action">
                      {/* «Оценить» только там, где анкета этого учителя про
                          ученика реально существует и не завершена. */}
                      {myAssessment && myAssessment.status !== 'completed' && (
                        <Button onClick={() => navigate(`/assessments/${myAssessment.id}`)}>
                          {myAssessment.status === 'not_started' ? 'Оценить' : 'Продолжить'}
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        onClick={() => navigate(`/teacher/students/${row.subject.id}`)}
                      >
                        Профиль
                      </Button>
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

      <Panel title="Средний профиль класса">
        {results.loading ? (
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
