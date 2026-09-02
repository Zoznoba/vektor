import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { fetchCases } from '../../api/cases';
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
