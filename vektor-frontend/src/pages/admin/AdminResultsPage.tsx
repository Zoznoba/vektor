import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Icon } from '../../components/icons/Icon';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import { useApi } from '../../hooks/useApi';
import { fetchUsers } from '../../api/users';
import { fetchClasses } from '../../api/classes';
import { classLabel } from '../../types/school';
import './admin.css';

/**
 * «Результаты» в админке — поиск ученика (по имени/email, опц. классу) и
 * переход к его индивидуальному профилю. Список фильтруется на бэкенде
 * (`GET /users?role=student&search=&class_id=`), а не на клиенте, как
 * «Пользователи»: тут сценарий именно поиск одного человека, не обзор всех.
 */
export function AdminResultsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const subjectId = id ? Number(id) : null;

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [classId, setClassId] = useState<number | null>(null);

  // Debounce: не дёргаем бэкенд на каждое нажатие клавиши.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const classes = useApi(fetchClasses);

  const loadStudents = useCallback(
    () =>
      fetchUsers({
        role: 'student',
        search: debouncedSearch || undefined,
        classId: classId ?? undefined,
      }),
    [debouncedSearch, classId],
  );
  const students = useApi(loadStudents);

  const classIndex = useMemo(() => {
    const index = new Map<number, string>();
    for (const cls of classes.data ?? []) {
      for (const s of cls.students) index.set(s.id, classLabel(cls));
    }
    return index;
  }, [classes.data]);

  if (subjectId !== null) {
    return (
      <AdminShell activeNavKey="results">
        <h2>Результаты ученика</h2>
        <div className="app-main__sub">
          <button type="button" className="link-button" onClick={() => navigate('/admin/results')}>
            ← к поиску
          </button>
        </div>
        <StudentResultsPanel subjectId={subjectId} title="Результаты" />
      </AdminShell>
    );
  }

  return (
    <AdminShell activeNavKey="results">
      <div className="admin-toolbar">
        <h2>Результаты</h2>
        <div className="admin-toolbar__spacer" />
        <select
          className="admin-select"
          value={classId ?? ''}
          onChange={(e) => setClassId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Все классы</option>
          {(classes.data ?? []).map((cls) => (
            <option key={cls.id} value={cls.id}>
              {classLabel(cls)}
            </option>
          ))}
        </select>
        <div className="search-box">
          <Icon name="search" size={16} />
          <input
            type="search"
            placeholder="Поиск ученика по имени или email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {students.error && <div className="form-error">{students.error}</div>}

      <Panel className="admin-table-panel">
        {students.loading ? (
          <div className="admin-empty">Загрузка…</div>
        ) : (students.data ?? []).length === 0 ? (
          <div className="admin-empty">Никого не нашлось</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Email</th>
                <th>Класс</th>
              </tr>
            </thead>
            <tbody>
              {(students.data ?? []).map((s) => (
                <tr key={s.id} onClick={() => navigate(`/admin/results/${s.id}`)}>
                  <td>{s.full_name}</td>
                  <td>{s.email}</td>
                  <td>{classIndex.get(s.id) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </AdminShell>
  );
}
