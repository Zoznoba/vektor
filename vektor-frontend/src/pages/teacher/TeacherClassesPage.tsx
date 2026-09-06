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

  const activeClass = myClasses.find((c) => c.id === selectedId) ?? myClasses[0] ?? null;
  const activeClassId = activeClass?.id ?? null;
  // Легенду показываем, только если у учителя ЕСТЬ классное руководство:
  // у предметника без него строка объясняла бы значок, которого нет.
  const hasHomeroom = myClasses.some((c) => isHomeroom(c, user?.id));

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
              // Значок «•» рисуется, а не пишется словами, поэтому полную
              // подпись даём кнопке целиком — иначе скринридер прочтёт «5-1».
              aria-label={
                isHomeroom(cls, user?.id)
                  ? `Класс ${classLabel(cls)}, вы классный руководитель`
                  : `Класс ${classLabel(cls)}`
              }
              onClick={() => setSelectedId(cls.id)}
            >
              {classLabel(cls)}
              {isHomeroom(cls, user?.id) && (
                <span className="teacher-chip__homeroom" aria-hidden="true">
                  •
                </span>
              )}
            </button>
          ))}
        </div>
        {myClasses.length > 0 && (
          <div className="teacher-head__note">
            {hasHomeroom && <span>• — классное руководство · </span>}
            Состав класса меняет администратор
          </div>
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
        activeClassId !== null && (
          <ClassDiagnostics
            key={activeClassId}
            classId={activeClassId}
            roleNote={activeClass ? myRoleNote(activeClass, user?.id) : null}
          />
        )
      )}
    </RoleShell>
  );
}

function isHomeroom(cls: SchoolClass, userId: number | undefined): boolean {
  return cls.teachers.some((t) => t.teacher.id === userId && t.is_homeroom);
}

/**
 * Чем учитель занят в ОТКРЫТОМ классе — подпись для заголовка состава.
 * Кл. руководство важнее предмета. `null`, когда предмет не заполнен: раньше
 * на его месте писалось слово «предмет», и у предметника оно повторялось на
 * каждом из дюжины чипов, ничего не сообщая.
 */
function myRoleNote(cls: SchoolClass, userId: number | undefined): string | null {
  const link = cls.teachers.find((t) => t.teacher.id === userId);
  if (link?.is_homeroom) return 'вы классный руководитель';
  return link?.subject ?? null;
}
