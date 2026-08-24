import { useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Icon } from '../../components/icons/Icon';
import { useApi } from '../../hooks/useApi';
import {
  fetchClasses,
  createClass,
  assignStudents,
  assignTeachers,
  assignHomeroom,
} from '../../api/classes';
import { fetchUsers, bulkCreateUsers } from '../../api/users';
import type { BulkUserIn } from '../../api/users';
import { ApiError } from '../../api/client';
import { classLabel } from '../../types/school';
import type { SchoolClass } from '../../types/school';
import type { User } from '../../types/auth';
import './admin.css';

export function AdminClassesPage() {
  const classes = useApi(fetchClasses);
  const users = useApi(fetchUsers);
  const location = useLocation();

  // Переход «Классы» из карточки учителя (AdminUsersPage) кладёт id класса
  // в state — так сразу открывается нужный класс, а не первый по сортировке.
  const [selectedId, setSelectedId] = useState<number | null>(
    () => (location.state as { classId?: number } | null)?.classId ?? null,
  );
  const [showCreate, setShowCreate] = useState(false);
  const [assignRole, setAssignRole] = useState<'student' | 'teacher' | null>(null);
  const [showHomeroom, setShowHomeroom] = useState(false);

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
                  {cls.homeroom_teacher
                    ? `Кл. рук.: ${cls.homeroom_teacher.full_name}`
                    : 'Кл. рук. не назначен'}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <Panel title={`Состав класса ${classLabel(selected)}`}>
              <div className="class-detail__teachers">
                <span>{teachersSummary(selected)}</span>
                <div className="admin-toolbar__spacer" />
                <Button variant="secondary" onClick={() => setShowHomeroom(true)}>
                  Кл. руководитель
                </Button>
                <Button variant="secondary" onClick={() => setAssignRole('teacher')}>
                  Добавить учителя
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
          allUsers={users.data ?? []}
          onClose={() => setShowCreate(false)}
          onCreated={(classId) => {
            setShowCreate(false);
            setSelectedId(classId);
            classes.reload();
            users.reload();
          }}
        />
      )}

      {showHomeroom && selected && (
        <HomeroomModal
          schoolClass={selected}
          allUsers={users.data ?? []}
          onClose={() => setShowHomeroom(false)}
          onAssigned={() => {
            setShowHomeroom(false);
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

/** «Классный руководитель: X · Также ведут: Y, Z» — как в концепте. */
function teachersSummary(cls: SchoolClass): string {
  const homeroom = cls.homeroom_teacher;
  const others = cls.teachers.filter((t) => t.id !== homeroom?.id);
  const parts: string[] = [];
  if (homeroom) parts.push(`Классный руководитель: ${homeroom.full_name}`);
  else parts.push('Классный руководитель не назначен');
  if (others.length > 0) parts.push(`Также ведут: ${others.map((t) => t.full_name).join(', ')}`);
  return parts.join(' · ');
}

function studentsCountLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ученик`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ученика`;
  return `${n} учеников`;
}

/** Одна распарсенная строка ростера. error !== null → строку нельзя отправлять. */
interface RosterRow {
  fullName: string;
  email: string;
  error: string | null;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Парсинг вставленного списка «ФИО<tab>email» (по строке на ученика).
 * Разделитель — таб (вставка из Excel) либо запятая/точка с запятой при
 * ручном вводе. Валидируем каждую строку: пустое ФИО, кривой/пустой email,
 * дубль внутри пачки, уже занятый в школе email — всё помечается, чтобы
 * админ починил ДО отправки (бэковый /users/bulk атомарен — либо всё, либо
 * ничего, так что частичной загрузки не будет).
 */
function parseRoster(raw: string, existingEmails: Set<string>): RosterRow[] {
  const rows: RosterRow[] = [];
  const seen = new Set<string>();
  for (const rawLine of raw.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;
    const [namePart = '', emailPart = ''] = line.split(/[\t,;]/);
    const fullName = namePart.trim();
    const email = emailPart.trim();
    const emailKey = email.toLowerCase();

    let error: string | null = null;
    if (!fullName) error = 'пустое ФИО';
    else if (!email) error = 'нет email';
    else if (!EMAIL_RE.test(email)) error = 'некорректный email';
    else if (existingEmails.has(emailKey)) error = 'email уже занят в школе';
    else if (seen.has(emailKey)) error = 'дубль в списке';

    if (email && !error) seen.add(emailKey);
    rows.push({ fullName, email, error });
  }
  return rows;
}

/**
 * Мастер «Новый класс» в два шага:
 *  1) параллель + литера + (опц.) классный руководитель;
 *  2) вставка списка учеников «ФИО<tab>email», превью с валидацией.
 * По кнопке: createClass → (опц.) assignHomeroom → bulkCreateUsers(class_id).
 * Порядок homeroom-перед-bulk выбран ради безопасного ретрая: если что-то
 * упало после создания класса, класс не пересоздаётся (createdClassId), а
 * homeroom-PUT идемпотентен — повторное нажатие «Создать» не ломается.
 */
function CreateClassModal({
  allUsers,
  onClose,
  onCreated,
}: {
  allUsers: User[];
  onClose: () => void;
  onCreated: (classId: number) => void;
}) {
  const [step, setStep] = useState<1 | 2>(1);
  const [grade, setGrade] = useState(1);
  const [section, setSection] = useState('');
  const [homeroomId, setHomeroomId] = useState<number | null>(null);
  const [roster, setRoster] = useState('');
  const [createdClassId, setCreatedClassId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const teachers = useMemo(() => allUsers.filter((u) => u.role === 'teacher'), [allUsers]);
  const existingEmails = useMemo(
    () => new Set(allUsers.map((u) => u.email.toLowerCase())),
    [allUsers],
  );

  const rows = useMemo(() => parseRoster(roster, existingEmails), [roster, existingEmails]);
  const errorCount = rows.filter((r) => r.error).length;
  const canSubmit = rows.length > 0 && errorCount === 0;

  const handleCreate = async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      let classId = createdClassId;
      if (classId === null) {
        const cls = await createClass(grade, section.trim());
        classId = cls.id;
        setCreatedClassId(classId); // ретрай не пересоздаёт класс
      }
      if (homeroomId !== null) await assignHomeroom(classId, homeroomId);
      const users: BulkUserIn[] = rows.map((r) => ({
        email: r.email,
        full_name: r.fullName,
        role: 'student',
      }));
      await bulkCreateUsers(users, classId);
      onCreated(classId);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && createdClassId === null) {
        setStep(1);
        setError('Такой класс уже существует');
      } else if (err instanceof ApiError && err.status === 409) {
        setError('Некоторые email уже заняты — поправьте список и попробуйте снова');
      } else if (err instanceof ApiError && err.status === 422) {
        // Бэк (Pydantic EmailStr) строже нашего превью: режет зарезервированные
        // домены (.test, example.com и т.п.), которые формально «похожи» на email.
        setError(
          'Бэкенд отклонил один из адресов как недопустимый email — обычно это ' +
            'зарезервированный домен вроде «@test.test» или «@example.com». ' +
            'Используйте реальный домен (например, @vektor.ru) и попробуйте снова.',
        );
      } else {
        setError(err instanceof ApiError ? err.message : 'Не удалось создать класс');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Новый класс · шаг ${step} из 2`} onClose={onClose}>
      {step === 1 ? (
        <div>
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
          <label className="form-field">
            <span>Классный руководитель (необязательно)</span>
            <select
              value={homeroomId ?? ''}
              onChange={(e) => setHomeroomId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— не назначать —</option>
              {teachers.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.full_name}
                </option>
              ))}
            </select>
          </label>

          {error && <div className="form-error">{error}</div>}

          <div className="modal__actions">
            <Button type="button" variant="secondary" onClick={onClose}>
              Отмена
            </Button>
            <Button onClick={() => setStep(2)} disabled={!section.trim()}>
              Далее
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <p className="roster-hint">
            Вставьте список учеников — по одному на строку в формате{' '}
            <strong>ФИО&nbsp;⇥&nbsp;email</strong> (можно скопировать два столбца прямо из
            Excel).
          </p>
          <textarea
            className="roster-input"
            value={roster}
            onChange={(e) => setRoster(e.target.value)}
            rows={7}
            placeholder={'Иванов Иван\tivanov.i@vektor.ru\nПетрова Анна\tpetrova.a@vektor.ru'}
            autoFocus
          />

          {rows.length > 0 && (
            <>
              <div className="roster-summary">
                Распознано: {rows.length}{' '}
                {errorCount === 0 ? (
                  <span className="roster-summary__ok">· ошибок нет ✓</span>
                ) : (
                  <span className="roster-summary__err">· с ошибками: {errorCount}</span>
                )}
              </div>
              <div className="roster-preview">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>ФИО</th>
                      <th>Email</th>
                      <th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i} className={r.error ? 'roster-row--error' : ''}>
                        <td>{r.fullName || <span className="roster-cell--empty">—</span>}</td>
                        <td>{r.email || <span className="roster-cell--empty">—</span>}</td>
                        <td>
                          {r.error ? (
                            <span className="roster-status roster-status--err">{r.error}</span>
                          ) : (
                            <span className="roster-status roster-status--ok">✓</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {error && <div className="form-error">{error}</div>}

          <div className="modal__actions">
            <Button type="button" variant="secondary" onClick={() => setStep(1)}>
              Назад
            </Button>
            <Button onClick={handleCreate} disabled={submitting || !canSubmit}>
              {submitting
                ? 'Создаём…'
                : `Создать класс и ${rows.length} ${studentsCountLabel(rows.length).split(' ')[1]}`}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function HomeroomModal({
  schoolClass,
  allUsers,
  onClose,
  onAssigned,
}: {
  schoolClass: SchoolClass;
  allUsers: User[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [teacherId, setTeacherId] = useState<number | null>(
    schoolClass.homeroom_teacher?.id ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Кандидат — любой учитель школы: если он ещё не ведёт класс,
  // бэкенд добавит его в учителя автоматически.
  const teachers = useMemo(() => allUsers.filter((u) => u.role === 'teacher'), [allUsers]);

  const handleSubmit = async () => {
    if (teacherId === null) return;
    setError(null);
    setSubmitting(true);
    try {
      await assignHomeroom(schoolClass.id, teacherId);
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось назначить руководителя');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Классный руководитель ${classLabel(schoolClass)}`} onClose={onClose}>
      {teachers.length === 0 ? (
        <div className="admin-empty">В школе пока нет ни одного учителя</div>
      ) : (
        <div className="assign-list">
          {teachers.map((t) => (
            <label key={t.id} className="assign-item">
              <input
                type="radio"
                name="homeroom"
                checked={teacherId === t.id}
                onChange={() => setTeacherId(t.id)}
              />
              <span className="assign-item__name">{t.full_name}</span>
              <span className="assign-item__email">{t.email}</span>
            </label>
          ))}
        </div>
      )}

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={submitting || teacherId === null || teacherId === schoolClass.homeroom_teacher?.id}
        >
          {submitting ? 'Сохраняем…' : 'Назначить'}
        </Button>
      </div>
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
