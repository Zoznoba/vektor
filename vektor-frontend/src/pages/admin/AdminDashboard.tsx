import { useMemo } from 'react';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { fetchUsers } from '../../api/users';
import { fetchClasses } from '../../api/classes';
import { fetchCases } from '../../api/cases';
import { fetchCampaigns } from '../../api/campaigns';
import './admin.css';
import { formatPeriod } from '../../data/period';

/** «Сводка» — метрики считаются из реальных /users, /classes, /cases и
 *  /campaigns. */
export function AdminDashboard() {
  const { user } = useAuth();
  const users = useApi(fetchUsers);
  const classes = useApi(fetchClasses);
  const cases = useApi(fetchCases);
  const campaigns = useApi(fetchCampaigns);

  const activeCampaigns = (campaigns.data ?? []).filter((c) => c.status === 'active');

  const counts = useMemo(() => {
    const list = users.data ?? [];
    return {
      students: list.filter((u) => u.role === 'student').length,
      teachers: list.filter((u) => u.role === 'teacher').length,
      parents: list.filter((u) => u.role === 'parent').length,
      classes: classes.data?.length ?? 0,
      cases: cases.data?.length ?? 0,
    };
  }, [users.data, classes.data, cases.data]);

  const metric = (value: number | string, label: string) => (
    <div className="metric">
      <div className="metric__value">
        {users.loading || classes.loading || cases.loading ? '…' : value}
      </div>
      <div className="metric__label">{label}</div>
    </div>
  );

  return (
    <AdminShell activeNavKey="dashboard">
      <h2>Сводка</h2>
      <div className="app-main__sub">Школа Вектор · {user?.academic_year}</div>

      {(users.error || classes.error || cases.error || campaigns.error) && (
        <div className="form-error">
          {users.error ?? classes.error ?? cases.error ?? campaigns.error}
        </div>
      )}

      <div className="metric-grid">
        {metric(counts.students, 'Учеников')}
        {metric(counts.teachers, 'Учителей')}
        {metric(counts.parents, 'Родителей')}
        {metric(counts.classes, 'Классов')}
        {metric(counts.cases, 'Кейсов')}
      </div>

      <Panel title="Активные кампании 360°">
        {campaigns.loading ? (
          <div className="admin-empty">Загрузка…</div>
        ) : activeCampaigns.length === 0 ? (
          <div className="admin-empty">
            Активных кампаний нет — создайте и запустите на странице «Диагностика»
          </div>
        ) : (
          <div className="profile-rows">
            {activeCampaigns.map((c) => (
              <div className="profile-row" key={c.id}>
                <span>
                  {c.title} · {formatPeriod(c.period_year, c.period_month)}
                </span>
                <span>
                  {c.completed_assessments} из {c.total_assessments} анкет
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </AdminShell>
  );
}
