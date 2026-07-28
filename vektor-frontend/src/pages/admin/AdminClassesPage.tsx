import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Icon } from '../../components/icons/Icon';
import { useApi } from '../../hooks/useApi';
import { fetchClasses, createClass, assignStudents, assignTeachers } from '../../api/classes';
import { fetchUsers } from '../../api/users';
import { ApiError } from '../../api/client';
import { classLabel } from '../../types/school';
import type { SchoolClass } from '../../types/school';
import type { User } from '../../types/auth';
import './admin.css';

export function AdminClassesPage() {
  const classes = useApi(fetchClasses);
  const users = useApi(fetchUsers);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [assignRole, setAssignRole] = useState<'student' | 'teacher' | null>(null);

  const sorted = useMemo(
    () =>
      [...(classes.data ?? [])].sort(
        (a, b) => a.grade - b.grade || a.section.localeCompare(b.section, 'ru'),
      ),
    [classes.data],
  );

  // Выбранный класс всегда берём из свежих данных (после reload объект новый);
  // пока ничего не выбрано — показываем первый, чтобы состав не был пустым экраном
  const selected = sorted.find((c) => c.id === selectedId) ?? sorted[0] ?? null;

  return (
    <AdminShell activeNavKey="classes">
      <div className="admin-toolbar">
        <h2>Классы</h2>
        <div className="admin-toolbar__spacer" />
        <Button onClick={() => setShowCreate(true)}>
          <Icon name="plus" size={15} />
          Добавить класс
        </Button>
      </div>

      {classes.error && <div className="form-error">{classes.error}</div>}

      {classes.loading ? (
        <Panel>
          <div className="admin-empty">Загрузка…</div>
        </Panel>
      ) : sorted.length === 0 ? (
        <Panel>
          <div className="admin-empty">
            Классов пока нет — создайте первый кнопкой «Добавить класс»
          </div>
        </Panel>
      ) : (
        <>
          <div className="class-grid">
            {sorted.map((cls) => (
              <button
                key={cls.id}
                className={`class-card ${cls.id === selected?.id ? 'class-card--selected' : ''}`.trim()}
                onClick={() => setSelectedId(cls.id)}
              >
                <div className="class-card__name">{classLabel(cls)}</div>
                <div className="class-card__count">{studentsCountLabel(cls.students.length)}</div>
                <div className="class-card__teachers">
                  {cls.teachers.length > 0
                    ? cls.teachers.map((t) => t.full_name).join(', ')
                    : 'Учитель не назначен'}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <Panel title={`Состав класса ${classLabel(selected)}`}>
              <div className="class-detail__teachers">
                {selected.teachers.length > 0 && (
                  <span>Учителя: {selected.teachers.map((t) => t.full_name).join(', ')}</span>
                )}
                <div className="admin-toolbar__spacer" />
                <Button variant="secondary" onClick={() => setAssignRole('teacher')}>
                  Назначить учителя
                </Button>
                <Button variant="secondary" onClick={() => setAssignRole('student')}>
                  Добавить учеников
                </Button>
              </div>

              {selected.students.length === 0 ? (
                <div className="admin-empty">В классе пока нет учеников</div>
              ) : (
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Ученик</th>
                      <th>Email</th>
                      <th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.students.map((s) => (
                      <tr key={s.id}>
                        <td>{s.full_name}</td>
                        <td>{s.email}</td>
                        <td>
                          <span
                            className={`status-dot ${s.is_active ? 'status-dot--on' : ''}`.trim()}
                          />
                          {s.is_active ? 'Активен' : 'Неактивен'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          )}
        </>
      )}

      {showCreate && (
        <CreateClassModal
          onClose={() => setShowCreate(false)}
          onCreated={(cls) => {
            setShowCreate(false);
            setSelectedId(cls.id);
            classes.reload();
          }}
        />
      )}

      {assignRole && selected && (
        <AssignModal
          role={assignRole}
          schoolClass={selected}
          allUsers={users.data ?? []}
          allClasses={classes.data ?? []}
          onClose={() => setAssignRole(null)}
          onAssigned={() => {
            setAssignRole(null);
            classes.reload();
          }}
        />
      )}
    </AdminShell>
  );
}

function studentsCountLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ученик`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ученика`;
  return `${n} учеников`;
}

function CreateClassModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (cls: SchoolClass) => void;
}) {
  const [grade, setGrade] = useState(1);
  const [section, setSection] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const cls = await createClass(grade, section.trim());
      onCreated(cls);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Такой класс уже существует');
      } else {
        setError(err instanceof ApiError ? err.message : 'Не удалось создать класс');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Новый класс" onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate>
        <label className="form-field">
          <span>Параллель (1–11)</span>
          <select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
            {Array.from({ length: 11 }, (_, i) => i + 1).map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Литера или номер (А, Б, 1…)</span>
          <input
            value={section}
            onChange={(e) => setSection(e.target.value)}
            placeholder="А"
            maxLength={10}
            required
          />
        </label>

        {error && <div className="form-error">{error}</div>}

        <div className="modal__actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" disabled={submitting || !section.trim()}>
            {submitting ? 'Создаём…' : 'Создать'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function AssignModal({
  role,
  schoolClass,
  allUsers,
  allClasses,
  onClose,
  onAssigned,
}: {
  role: 'student' | 'teacher';
  schoolClass: SchoolClass;
  allUsers: User[];
  allClasses: SchoolClass[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Кандидаты: ученики — без класса вообще (у ученика класс один),
  // учителя — все, кто ещё не ведёт ЭТОТ класс (учитель может вести несколько).
  const candidates = useMemo(() => {
    if (role === 'student') {
      const assigned = new Set(allClasses.flatMap((c) => c.students.map((s) => s.id)));
      return allUsers.filter((u) => u.role === 'student' && !assigned.has(u.id));
    }
    const inThisClass = new Set(schoolClass.teachers.map((t) => t.id));
    return allUsers.filter((u) => u.role === 'teacher' && !inThisClass.has(u.id));
  }, [role, allUsers, allClasses, schoolClass]);

  const toggle = (id: number) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const ids = [...checked];
      if (role === 'student') await assignStudents(schoolClass.id, ids);
      else await assignTeachers(schoolClass.id, ids);
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить назначение');
    } finally {
      setSubmitting(false);
    }
  };

  const title =
    role === 'student'
      ? `Ученики в класс ${classLabel(schoolClass)}`
      : `Учителя класса ${classLabel(schoolClass)}`;

  return (
    <Modal title={title} onClose={onClose}>
      {candidates.length === 0 ? (
        <div className="admin-empty">
          {role === 'student'
            ? 'Свободных учеников нет — все уже распределены по классам'
            : 'Все учителя уже ведут этот класс (или учителей нет вовсе)'}
        </div>
      ) : (
        <div className="assign-list">
          {candidates.map((u) => (
            <label key={u.id} className="assign-item">
              <input type="checkbox" checked={checked.has(u.id)} onChange={() => toggle(u.id)} />
              <span className="assign-item__name">{u.full_name}</span>
              <span className="assign-item__email">{u.email}</span>
            </label>
          ))}
        </div>
      )}

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting || checked.size === 0}>
          {submitting ? 'Сохраняем…' : `Назначить (${checked.size})`}
        </Button>
      </div>
    </Modal>
  );
}
