import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { useApi } from '../../hooks/useApi';
import { fetchUsers } from '../../api/users';
import { fetchClasses } from '../../api/classes';
import './admin.css';

/**
 * «Сводка» — метрики считаются из реальных /users и /classes.
 * Блок активных 360-тестов появится после Этапа 4 бэкенда.
 */
export function AdminDashboard() {
  const users = useApi(fetchUsers);
  const classes = useApi(fetchClasses);
  const navigate = useNavigate();

  const counts = useMemo(() => {
    const list = users.data ?? [];
    return {
      students: list.filter((u) => u.role === 'student').length,
      teachers: list.filter((u) => u.role === 'teacher').length,
      parents: list.filter((u) => u.role === 'parent').length,
      classes: classes.data?.length ?? 0,
    };
  }, [users.data, classes.data]);

  const metric = (value: number | string, label: string) => (
    <div className="metric">
      <div className="metric__value">{users.loading || classes.loading ? '…' : value}</div>
      <div className="metric__label">{label}</div>
    </div>
  );

  return (
    <AdminShell activeNavKey="dashboard">
      <h2>Сводка</h2>
      <div className="app-main__sub">Школа Вектор · учебный год 2025–2026</div>

      {(users.error || classes.error) && (
        <div className="form-error">{users.error ?? classes.error}</div>
      )}

      <div className="metric-grid">
        {metric(counts.students, 'Учеников')}
        {metric(counts.teachers, 'Учителей')}
        {metric(counts.parents, 'Родителей')}
        {metric(counts.classes, 'Классов')}
      </div>

      <Panel title="Активные 360-тесты">
        <div className="admin-empty">
          Тестов пока нет — конструктор 360-тестов появится вместе с модулем anketing
          на бэкенде (Этап 4)
        </div>
      </Panel>

      <Panel title="Быстрые действия">
        <div className="quick-actions">
          <Button variant="secondary" onClick={() => navigate('/admin/users')}>
            Пользователи
          </Button>
          <Button variant="secondary" onClick={() => navigate('/admin/classes')}>
            Классы
          </Button>
        </div>
      </Panel>
    </AdminShell>
  );
}
