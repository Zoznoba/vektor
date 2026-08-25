import { useEffect, useState } from 'react';
import { RoleShell } from '../../components/layout/RoleShell';
import { Panel } from '../../components/ui/Panel';
import { Avatar } from '../../components/ui/Avatar';
import { StudentResultsPanel } from '../../components/dashboard/StudentResultsPanel';
import { useAuth } from '../../auth/AuthContext';
import { fetchChildren } from '../../api/users';
import { ApiError } from '../../api/client';
import type { User } from '../../types/auth';
import './ParentResultsPage.css';

/**
 * «Результаты» родителя — по умолчанию первый ребёнок, переключатель
 * появляется только при 2+ детях (при одном ребёнке пилюля-переключатель —
 * лишний элемент интерфейса без выбора).
 */
export function ParentResultsPage() {
  const { user } = useAuth();
  const [children, setChildren] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    fetchChildren(user.id)
      .then((list) => {
        if (cancelled) return;
        setChildren(list);
        setSelectedId(list[0]?.id ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Не удалось загрузить детей');
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!user) return null;

  return (
    <RoleShell activeNavKey="results">
      <h2>Результаты</h2>
      <div className="app-main__sub">Результаты вашего ребёнка</div>

      {error && <div className="form-error">{error}</div>}

      {children === null ? (
        <Panel>
          <div className="app-main__sub">Загрузка…</div>
        </Panel>
      ) : children.length === 0 ? (
        <Panel>
          <div className="app-main__sub">
            Пока не привязано ни одного ребёнка. Обратитесь к администратору школы.
          </div>
        </Panel>
      ) : (
        <>
          {children.length > 1 && (
            <div className="child-switcher">
              {children.map((child) => (
                <button
                  key={child.id}
                  type="button"
                  className={`child-switcher__item ${
                    child.id === selectedId ? 'child-switcher__item--active' : ''
                  }`.trim()}
                  onClick={() => setSelectedId(child.id)}
                >
                  <Avatar fullName={child.full_name} className="child-switcher__avatar" />
                  {child.full_name}
                </button>
              ))}
            </div>
          )}

          {selectedId !== null && (
            <StudentResultsPanel subjectId={selectedId} title="Результаты" />
          )}
        </>
      )}
    </RoleShell>
  );
}
