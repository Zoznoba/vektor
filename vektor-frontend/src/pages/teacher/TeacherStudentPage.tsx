import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { Panel } from '../../components/ui/Panel';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { fetchClasses } from '../../api/classes';
import { classLabel } from '../../types/school';
import './TeacherStudentPage.css';

/**
 * «Профиль ученика» — индивидуальные результаты одного ученика глазами учителя.
 *
 * Без выбранного ученика показываем список тех, к кому у учителя есть доступ:
 * ученики его классов. Права всё равно проверяет бэкенд (учитель класса или
 * родитель), список здесь — навигация, а не защита.
 */
export function TeacherStudentPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const classes = useApi(fetchClasses);

  const myClasses = useMemo(
    () => (classes.data ?? []).filter((c) => c.teachers.some((t) => t.id === user?.id)),
    [classes.data, user?.id],
  );

  const subjectId = id ? Number(id) : null;

  // Имя выбранного ученика ищем в составе классов — отдельного запроса за
  // пользователем не делаем: он уже приехал вместе со списком классов.
  const subjectName = useMemo(() => {
    for (const cls of myClasses) {
      const found = cls.students.find((s) => s.id === subjectId);
      if (found) return found.full_name;
    }
    return null;
  }, [myClasses, subjectId]);

  if (subjectId !== null) {
    return (
      <RoleShell activeNavKey="students">
        <h2>{subjectName ?? 'Профиль ученика'}</h2>
        <div className="app-main__sub">
          <button type="button" className="link-button" onClick={() => navigate('/teacher/students')}>
            ← ко всем ученикам
          </button>
        </div>
        <StudentResultsPanel subjectId={subjectId} title="Результаты ученика" />
      </RoleShell>
    );
  }

  return (
    <RoleShell activeNavKey="students">
      <h2>Профиль ученика</h2>
      <div className="app-main__sub">Выберите ученика, чтобы посмотреть его результаты</div>

      {classes.loading ? (
        <Panel>
          <div className="app-main__sub">Загрузка…</div>
        </Panel>
      ) : myClasses.length === 0 ? (
        <Panel>
          <div className="app-main__sub">
            К вам пока не привязан ни один класс. Состав классов назначает администратор.
          </div>
        </Panel>
      ) : (
        myClasses.map((cls) => (
          <Panel key={cls.id} title={`${classLabel(cls)} · ${cls.students.length} учеников`}>
            <div className="student-grid">
              {cls.students.map((student) => (
                <button
                  key={student.id}
                  type="button"
                  className="student-card"
                  onClick={() => navigate(`/teacher/students/${student.id}`)}
                >
                  {student.full_name}
                </button>
              ))}
            </div>
          </Panel>
        ))
      )}
    </RoleShell>
  );
}
