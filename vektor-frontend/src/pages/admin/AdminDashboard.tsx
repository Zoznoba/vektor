import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Collapsible } from '../../components/ui/Collapsible';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { SchoolAnalytics } from '../../components/dashboard/SchoolAnalytics';
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

  const [analyticsOpen, setAnalyticsOpen] = useState(true);

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

  const metric = (
    value: number | string,
    label: string,
    to: string,
    state?: Record<string, unknown>,
  ) => (
    <Link className="metric" to={to} state={state}>
      <div className="metric__value">
        {users.loading || classes.loading || cases.loading ? '…' : value}
      </div>
      <div className="metric__label">{label}</div>
    </Link>
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

      {/* «Что сейчас идёт» — полоской СРАЗУ под заголовком, а не панелью
          внизу экрана: это единственное на сводке, что требует действия
          сегодня, а панель под длинной аналитикой требовала прокрутки, чтобы
          узнать, идёт ли диагностика вообще. Строка на кампанию, клик ведёт
          на «Диагностику» с открытой карточкой.

          Активных нет — полоски нет вовсе: пустая строка «активных кампаний
          нет» занимала бы место ради отсутствия новости. Пояснение, где их
          заводят, осталось на самом экране «Диагностика». */}
      {activeCampaigns.length > 0 && (
        <div className="running-campaigns">
          {activeCampaigns.map((c) => {
            const percent =
              c.total_assessments > 0 ? (c.completed_assessments / c.total_assessments) * 100 : 0;
            return (
              <Link
                className="running-campaign"
                key={c.id}
                to="/admin/campaigns"
                state={{ campaignId: c.id }}
              >
                <span className="running-campaign__dot" />
                <span className="running-campaign__title">
                  {c.title} · {formatPeriod(c.period_year, c.period_month)}
                </span>
                {/* Синяя, а не лаймовая: лайм в проекте — «выросло, хорошо»,
                    а здесь полоса показывает ход работы, а не результат. */}
                <ProgressBar value={percent} variant="blue" className="running-campaign__bar" />
                <span className="running-campaign__counts">
                  {c.completed_assessments} из {c.total_assessments} анкет
                </span>
                <span className="running-campaign__percent">{Math.round(percent)}%</span>
              </Link>
            );
          })}
        </div>
      )}

      <div className="metric-grid">
        {metric(counts.students, 'Учеников', '/admin/users', { roleFilter: 'student' })}
        {metric(counts.teachers, 'Учителей', '/admin/users', { roleFilter: 'teacher' })}
        {metric(counts.parents, 'Родителей', '/admin/users', { roleFilter: 'parent' })}
        {metric(counts.classes, 'Классов', '/admin/classes')}
        {metric(counts.cases, 'Кейсов', '/admin/cases')}
      </div>

      {/* Аналитика школы — ниже счётчиков состава и выше кампаний: сводка
          отвечает сначала «кто в школе», потом «как школа выглядит», и только
          потом «что сейчас идёт».

          Сворачиваемый блок, как аналитика класса и кейса (7r): экран длинный,
          и «что сейчас идёт» должно оставаться в досягаемости. Раскрыт по
          умолчанию, в отличие от класса: там под ним рабочий состав, а здесь
          аналитика и есть содержимое сводки. */}
      <Collapsible
        title="Аналитика по школе"
        hint="Профиль школы, зоны роста и классы по среднему баллу"
        open={analyticsOpen}
        onToggle={() => setAnalyticsOpen((value) => !value)}
      >
        <SchoolAnalytics />
      </Collapsible>

    </AdminShell>
  );
}
