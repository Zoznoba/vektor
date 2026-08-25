import { useMemo, useState } from 'react';
import { RoleShell } from '../../components/layout/RoleShell';
import { ClassDiagnostics } from './ClassDiagnostics';
import { useApi } from '../../hooks/useApi';
import { useAuth } from '../../auth/AuthContext';
import { fetchClasses } from '../../api/classes';
import { classLabel } from '../../types/school';
import type { SchoolClass } from '../../types/school';
import './TeacherClassesPage.css';

/**
 * «Мои классы» — стартовый экран учителя (прототип, роль teacher).
 *
 * Свои классы отбираем на фронте: /classes отдаёт все классы школы, но в
 * каждом есть список teachers, и классный руководитель туда входит по
 * построению. Отдельный эндпоинт «мои классы» заводить не стали — школа
 * маленькая, а лишний контракт пришлось бы держать в синхронизации.
 */
export function TeacherClassesPage() {
  const { user } = useAuth();
  const classes = useApi(fetchClasses);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const myClasses = useMemo(
    () => (classes.data ?? []).filter((c) => c.teachers.some((t) => t.teacher.id === user?.id)),
    [classes.data, user?.id],
  );

  const activeClassId = selectedId ?? myClasses[0]?.id ?? null;

  return (
    <RoleShell activeNavKey="classes">
      <div className="teacher-head">
        <h2>Мои классы</h2>
        <div className="teacher-chips">
          {myClasses.map((cls) => (
            <button
              key={cls.id}
              type="button"
              className={`teacher-chip ${
                cls.id === activeClassId ? 'teacher-chip--active' : ''
              }`.trim()}
              onClick={() => setSelectedId(cls.id)}
            >
              {classLabel(cls)}
              <span className="teacher-chip__tag">
                {myRoleTag(cls, user?.id)}
              </span>
            </button>
          ))}
        </div>
        {myClasses.length > 0 && (
          <div className="teacher-head__note">Состав класса меняет администратор</div>
        )}
      </div>

      {classes.loading ? (
        <div className="app-main__sub">Загрузка…</div>
      ) : myClasses.length === 0 ? (
        <div className="app-main__sub">
          К вам пока не привязан ни один класс. Состав классов назначает администратор.
        </div>
      ) : (
        // key — чтобы смена класса пересоздавала блок, а не подмешивала
        // данные прошлого класса в новый рендер.
        activeClassId !== null && <ClassDiagnostics key={activeClassId} classId={activeClassId} />
      )}
    </RoleShell>
  );
}

/**
 * Подпись роли на чипе класса: кл. руководство важнее предмета, а предмет
 * («литература») информативнее слова «предмет» — но у старых связей его нет.
 */
function myRoleTag(cls: SchoolClass, userId: number | undefined): string {
  const link = cls.teachers.find((t) => t.teacher.id === userId);
  if (link?.is_homeroom) return 'кл. рук.';
  return link?.subject ?? 'предмет';
}
