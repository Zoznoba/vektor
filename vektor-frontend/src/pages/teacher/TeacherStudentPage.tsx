import { useNavigate, useParams } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import './TeacherStudentPage.css';

/**
 * «Профиль ученика» — индивидуальные результаты одного ученика глазами учителя.
 *
 * Своего пункта в сайдбаре у экрана нет: сюда ведут строки состава из
 * «Моих классов» (диагностика класса) и «Моих кейсов». Права проверяет
 * бэкенд — учитель класса ученика, руководитель его кейса или родитель.
 */
export function TeacherStudentPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const subjectId = id ? Number(id) : null;

  return (
    <RoleShell activeNavKey="">
      <h2>Профиль ученика</h2>
      <div className="app-main__sub">
        <button type="button" className="link-button" onClick={() => navigate(-1)}>
          ← назад
        </button>
      </div>
      {subjectId !== null && (
        /* Имя показывает сама StudentResultsPanel (шапка «кого мы смотрим»,
           из subject в /results/{id}) — здесь дублировать не нужно. */
        <StudentResultsPanel subjectId={subjectId} title="Результаты ученика" />
      )}
    </RoleShell>
  );
}
