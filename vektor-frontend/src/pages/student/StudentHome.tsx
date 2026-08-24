import { useNavigate } from 'react-router-dom';
import { RoleShell } from '../../components/layout/RoleShell';
import { InfoBanner } from '../../components/dashboard/InfoBanner';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import { useAuth } from '../../auth/AuthContext';
import { useApi } from '../../hooks/useApi';
import { fetchMyAssessments } from '../../api/assessments';

/** «Иванова Полина» → «Полина»; если слово одно — оно и есть имя. */
function firstNameOf(fullName: string): string {
  const words = fullName.trim().split(/\s+/);
  return words[1] ?? words[0];
}

/**
 * Экран 1 из ТЗ (п. 4.7) — «Личный кабинет ученика».
 *
 * Заполнение анкет отсюда ушло в раздел «Анкеты»: два места с одним и тем же
 * списком расходились бы по счётчикам. Здесь остаётся напоминание со ссылкой
 * туда и собственные результаты ученика.
 */
export function StudentHome() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const assessments = useApi(fetchMyAssessments);
  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const pendingItems = (assessments.data ?? []).filter((a) => a.status !== 'completed');
  const pendingCount = pendingItems.length;

  return (
    <RoleShell activeNavKey="home">
      <h2>Добрый день, {firstNameOf(user.full_name)}</h2>
      <div className="app-main__sub">
        {user.class_label ? `${user.class_label} класс · ` : ''}
        {user.academic_year}
      </div>

      {pendingCount > 0 && (
        <InfoBanner actionLabel="Перейти к анкетам" onAction={() => navigate('/surveys')}>
          {/* Дедлайна в тексте нет: окно приёма (campaigns.opens_at /
              closes_at) удалено — оно ничего не ограничивало, приём режется
              статусом кампании. */}
          Ждут заполнения {pendingCount} {pendingCount === 1 ? 'анкета' : 'анкеты'}
        </InfoBanner>
      )}

      <StudentResultsPanel subjectId={user.id} />
    </RoleShell>
  );
}
