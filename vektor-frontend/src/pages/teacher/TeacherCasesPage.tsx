import { useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { fetchCases } from '../../api/cases';
import { fetchCaseResults } from '../../api/results';
import { RadarChart } from '../../components/charts/RadarChart';
import { shortCompetencyName } from '../../data/competencyShortNames';
import { formatPeriod } from '../../data/period';
import type { Case } from '../../types/case';
import type { User } from '../../types/auth';
import './TeacherClassesPage.css';

/**
 * «Мои кейсы» — экран профильной группы у учителя.
 *
 * Свой кейс отбираем на фронте из общего /cases — тем же приёмом, что «Мои
 * классы» отбирают классы из /classes: школа маленькая, а отдельный эндпоинт
 * пришлось бы держать в синхронизации с этим.
 *
 * Переключателя между кейсами тут нет намеренно, в отличие от классов:
 * членство в кейсе РОВНО ОДНО и у ученика, и у учителя — это гарантирует
 * схема (FK users.case_id, см. CLAUDE.md, Этап 8), поэтому кейс у учителя
 * либо один, либо ни одного.
 *
 * Состав кейса read-only: его назначает админ (как и состав класса).
 *
 * А вот результаты ученика по клику открываются: право на них даёт членство
 * в кейсе наравне с учительством в классе (can_view_results, решение
 * заказчика от 2026-09-02) — иначе руководитель кружка не видел бы данных
 * собственных подопечных, ведь они по определению из разных классов.
 */
export function TeacherCasesPage() {
  const { user } = useAuth();
  const cases = useApi(fetchCases);

  const myCase = useMemo(
    () => (cases.data ?? []).find((c) => c.teachers.some((t) => t.id === user?.id)) ?? null,
    [cases.data, user?.id],
  );

  return (
    <RoleShell activeNavKey="cases">
      <div className="teacher-head">
        <h2>Мои кейсы</h2>
        {myCase && <div className="teacher-head__note">Состав кейса меняет администратор</div>}
      </div>

      {cases.error && <div className="form-error">{cases.error}</div>}

      {cases.loading && !cases.data ? (
        <div className="app-main__sub">Загрузка…</div>
      ) : myCase === null ? (
        <div className="app-main__sub">
          Вы пока не привязаны ни к одному кейсу. Профильные группы назначает администратор.
        </div>
      ) : (
        <CaseOverview kase={myCase} currentUserId={user?.id} />
      )}
    </RoleShell>
  );
}

function CaseOverview({ kase, currentUserId }: { kase: Case; currentUserId: number | undefined }) {
  // Себя из списка коллег убираем: «кто ещё ведёт этот кейс» — вот что
  // учителю действительно неизвестно, а собственное имя он и так знает.
  const colleagues = kase.teachers.filter((t) => t.id !== currentUserId);

  return (
    <>
      <Panel title={`Кейс «${kase.name}»`}>
        {kase.description && <p className="app-main__sub">{kase.description}</p>}
        <div className="teacher-metrics">
          <div className="teacher-metric">
            <div className="teacher-metric__value teacher-metric__value--blue">
              {kase.students.length}
            </div>
            <div className="teacher-metric__label">Учеников в кейсе</div>
          </div>
          <div className="teacher-metric">
            <div className="teacher-metric__value">{kase.teachers.length}</div>
            <div className="teacher-metric__label">Учителей ведут кейс</div>
          </div>
          <div className="teacher-metric">
            <div className="teacher-metric__value">{colleagues.length}</div>
            <div className="teacher-metric__label">
              {colleagues.length === 0
                ? 'Вы ведёте кейс один'
                : colleagues.map((t) => t.full_name).join(', ')}
            </div>
          </div>
        </div>
      </Panel>

      <CaseProfilePanel caseId={kase.id} caseName={kase.name} />

      <Panel title="Ученики">
        {kase.students.length === 0 ? (
          <div className="app-main__sub">
            В кейсе пока нет учеников — их привязывает администратор.
          </div>
        ) : (
          <div className="roster-scroll">
            <table className="roster">
              <thead>
                <tr>
                  <th>Ученик</th>
                  <th>Email</th>
                  <th>Статус</th>
                  <th className="roster__action" />
                </tr>
              </thead>
              <tbody>
                {kase.students.map((student) => (
                  <StudentRow key={student.id} student={student} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

function StudentRow({ student }: { student: User }) {
  const navigate = useNavigate();

  return (
    <tr>
      <td className="roster__name">{student.full_name}</td>
      <td className="roster__muted">{student.email}</td>
      <td>
        <span
          className={`roster__status ${student.is_active ? 'roster__status--completed' : ''}`.trim()}
        >
          {student.is_active ? 'Активен' : 'Неактивен'}
        </span>
      </td>
      <td className="roster__action">
        {/* Тот же экран профиля ученика, что и у учителя класса, — панель
            результатов одна на все роли. */}
        <Button variant="secondary" onClick={() => navigate(`/teacher/students/${student.id}`)}>
          Результаты
        </Button>
      </td>
    </tr>
  );
}

/**
 * Средний профиль кейса против школы — тот же радар и та же логика, что на
 * экране класса («Средний профиль класса»).
 *
 * Зачем он тут, если результаты каждого ученика открываются поштучно:
 * поштучно не видно, чем группа отличается от школы в целом, а кружок для
 * того и собирают. Сравнение идёт со ШКОЛОЙ, а не с классами участников, —
 * учеников кейса по определению набирают из разных классов, и «свой класс»
 * у группы просто не определён.
 *
 * 404 здесь штатный: кейс мог ни разу не попасть в кампанию (кампании
 * собирались только по классам до 2026-09-02). Отличаем его от реального
 * сбоя по status, а не по тексту ошибки.
 */
function CaseProfilePanel({ caseId, caseName }: { caseId: number; caseName: string }) {
  // useApi требует стабильную ссылку — иначе effect уходит в цикл запросов.
  const loadResults = useCallback(() => fetchCaseResults(caseId), [caseId]);
  const results = useApi(loadResults);

  const radar = useMemo(() => {
    // Оси только там, где есть хоть одно значение: критерий, закрытый по
    // возрасту (профпробы до 9 класса), дал бы пустой луч и перекосил фигуру.
    const scored = (results.data?.competencies ?? []).filter(
      (c) => c.case_avg !== null || c.school_avg !== null,
    );
    return {
      axes: scored.map((c) => shortCompetencyName(c.code, c.name)),
      titles: scored.map((c) => c.name),
      caseValues: scored.map((c) => c.case_avg),
      schoolValues: scored.map((c) => c.school_avg),
    };
  }, [results.data]);

  if (results.loading && !results.data) {
    return (
      <Panel title="Профиль кейса">
        <div className="app-main__sub">Загрузка…</div>
      </Panel>
    );
  }

  if (results.error || !results.data) {
    return (
      <Panel title="Профиль кейса">
        <div className="app-main__sub">
          {results.status === 404
            ? 'Диагностики по этому кейсу ещё не было — профиль появится после первой завершённой кампании.'
            : results.error}
        </div>
      </Panel>
    );
  }

  const data = results.data;

  return (
    <>
      <Panel title="Профиль кейса">
        <div className="app-main__sub">
          {data.campaign_title} ·{' '}
          {formatPeriod(data.campaign_period_year, data.campaign_period_month)} · результаты по{' '}
          {data.students_with_results} ученикам
        </div>

        <div className="teacher-metrics">
          <div className="teacher-metric">
            <div className="teacher-metric__value teacher-metric__value--blue">
              {data.case_average === null ? '—' : data.case_average.toFixed(2)}
            </div>
            <div className="teacher-metric__label">Средний балл кейса</div>
          </div>
          <div className="teacher-metric">
            <div className="teacher-metric__value">
              {data.school_average === null ? '—' : data.school_average.toFixed(2)}
            </div>
            <div className="teacher-metric__label">Средний по школе за период</div>
          </div>
        </div>

        {radar.axes.length >= 3 ? (
          <RadarChart
            axes={radar.axes}
            axisTitles={radar.titles}
            series={[
              { label: `Кейс «${caseName}»`, values: radar.caseValues, color: 'var(--blue)' },
              { label: 'Школа', values: radar.schoolValues, color: '#a6a2a3', dashed: true },
            ]}
          />
        ) : (
          /* Радар — единственное представление профиля, поэтому у вырожденного
             набора осей нужна явная строка, а не пустота. */
          <div className="app-main__sub">Критериев с баллом слишком мало для профиля</div>
        )}
      </Panel>

      {data.growth_zones.length > 0 && (
        <Panel title="Зоны роста кейса">
          {/* Ранжирование по ОХВАТУ, а не по худшему среднему: это темы для
              занятий группы, а не список слабых учеников. */}
          <div className="app-main__sub">
            У скольких учеников критерий попал в личные зоны роста
          </div>
          {data.growth_zones.map((zone) => (
            <div className="growth-zone" key={zone.competency_id}>
              <div className="growth-zone__score">
                {zone.case_avg === null ? '—' : zone.case_avg.toFixed(1)}
              </div>
              <div className="growth-zone__name">{zone.name}</div>
              <div className="growth-zone__count">{zone.students_affected} учеников</div>
            </div>
          ))}
        </Panel>
      )}
    </>
  );
}
