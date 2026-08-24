import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Icon } from '../../components/icons/Icon';
import { ActionMenu } from '../../components/ui/ActionMenu';
import type { ActionMenuItem } from '../../components/ui/ActionMenu';
import { useApi } from '../../hooks/useApi';
import {
  fetchClasses,
  createClass,
  assignStudents,
  assignTeachers,
  updateTeacherInClass,
  removeTeacherFromClass,
  removeStudentFromClass,
} from '../../api/classes';
import { fetchUsers, bulkCreateUsers } from '../../api/users';
import type { BulkUserIn } from '../../api/users';
import { ApiError } from '../../api/client';
import { classLabel, homeroomTeachers } from '../../types/school';
import type { SchoolClass, TeacherInClass } from '../../types/school';
import type { User } from '../../types/auth';
import './admin.css';

/** Вкладки состава класса. Определяют и таблицу, и контекстную кнопку добавления. */
type CompositionTab = 'students' | 'teachers' | 'homeroom';

const TABS: { key: CompositionTab; label: string }[] = [
  { key: 'students', label: 'Ученики' },
  { key: 'teachers', label: 'Учителя' },
  { key: 'homeroom', label: 'Классное руководство' },
];

export function AdminClassesPage() {
  const classes = useApi(fetchClasses);
  const users = useApi(fetchUsers);
  const location = useLocation();

  // Переход «Классы» из карточки учителя (AdminUsersPage) кладёт id класса
  // в state — так сразу открывается нужный класс, а не первый по сортировке.
  const [selectedId, setSelectedId] = useState<number | null>(
    () => (location.state as { classId?: number } | null)?.classId ?? null,
  );
  const [tab, setTab] = useState<CompositionTab>('students');
  const [showCreate, setShowCreate] = useState(false);
  // Модалка назначения: режим совпадает с активной вкладкой — «добавить» на
  // вкладке всегда добавляет именно тех, кого эта вкладка показывает.
  const [assignMode, setAssignMode] = useState<CompositionTab | null>(null);
  const [editSubjectFor, setEditSubjectFor] = useState<TeacherInClass | null>(null);
  const [transferStudent, setTransferStudent] = useState<User | null>(null);
  const [detaching, setDetaching] = useState<DetachTarget | null>(null);

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

  const addLabel: Record<CompositionTab, string> = {
    students: 'Добавить учеников',
    teachers: 'Добавить учителя',
    homeroom: 'Назначить руководителя',
  };

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

      {/* Спиннер только на ПЕРВОЙ загрузке: reload после мутации оставляет
          данные на экране, а подмена всего блока размонтировала бы панель
          вместе с её состоянием — сообщение о результате исчезало. */}
      {classes.loading && !classes.data ? (
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
                <div className="class-card__teachers">{teachersCountLabel(cls.teachers.length)}</div>
              </button>
            ))}
          </div>

          {selected && (
            <Panel title={`Состав класса ${classLabel(selected)}`}>
              <div className="class-tabs">
                <div className="filter-chips">
                  {TABS.map((t) => (
                    <button
                      key={t.key}
                      className={`filter-chip ${tab === t.key ? 'filter-chip--active' : ''}`.trim()}
                      onClick={() => setTab(t.key)}
                    >
                      {t.label} · {countFor(selected, t.key)}
                    </button>
                  ))}
                </div>
                <div className="admin-toolbar__spacer" />
                <Button variant="secondary" onClick={() => setAssignMode(tab)}>
                  <Icon name="plus" size={15} />
                  {addLabel[tab]}
                </Button>
              </div>

              {tab === 'students' ? (
                <StudentsTable
                  schoolClass={selected}
                  onTransfer={setTransferStudent}
                  onDetach={(student) =>
                    setDetaching({ kind: 'student', user: student, schoolClass: selected })
                  }
                />
              ) : (
                <TeachersTable
                  schoolClass={selected}
                  rows={tab === 'homeroom' ? homeroomTeachers(selected) : selected.teachers}
                  showHomeroomColumn={tab === 'teachers'}
                  onEditSubject={setEditSubjectFor}
                  onToggleHomeroom={async (link) => {
                    await updateTeacherInClass(selected.id, link.teacher.id, {
                      is_homeroom: !link.is_homeroom,
                    });
                    classes.reload();
                  }}
                  onDetach={(link) =>
                    setDetaching({ kind: 'teacher', user: link.teacher, schoolClass: selected })
                  }
                />
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

      {assignMode && selected && (
        <AssignModal
          mode={assignMode}
          schoolClass={selected}
          allUsers={users.data ?? []}
          allClasses={classes.data ?? []}
          onClose={() => setAssignMode(null)}
          onAssigned={() => {
            setAssignMode(null);
            classes.reload();
          }}
        />
      )}

      {editSubjectFor && selected && (
        <SubjectModal
          schoolClass={selected}
          link={editSubjectFor}
          onClose={() => setEditSubjectFor(null)}
          onSaved={() => {
            setEditSubjectFor(null);
            classes.reload();
          }}
        />
      )}

      {transferStudent && selected && (
        <TransferModal
          student={transferStudent}
          from={selected}
          allClasses={sorted}
          onClose={() => setTransferStudent(null)}
          onTransferred={() => {
            setTransferStudent(null);
            classes.reload();
          }}
        />
      )}

      {detaching && (
        <DetachModal
          target={detaching}
          onClose={() => setDetaching(null)}
          onDetached={() => {
            setDetaching(null);
            classes.reload();
          }}
        />
      )}
    </AdminShell>
  );
}

interface DetachTarget {
  kind: 'student' | 'teacher';
  user: User;
  schoolClass: SchoolClass;
}

function countFor(cls: SchoolClass, tab: CompositionTab): number {
  if (tab === 'students') return cls.students.length;
  if (tab === 'teachers') return cls.teachers.length;
  return homeroomTeachers(cls).length;
}

/** Пункты «профиль» и «результаты» — общие для любой роли в составе класса. */
function commonUserActions(user: User, navigate: ReturnType<typeof useNavigate>): ActionMenuItem[] {
  const items: ActionMenuItem[] = [
    {
      key: 'profile',
      label: 'Открыть профиль',
      onSelect: () => navigate('/admin/users', { state: { userId: user.id } }),
    },
  ];
  // Результаты есть только у ученика: субъект диагностики — он, учитель
  // выступает оценивающим и собственного профиля результатов не имеет.
  if (user.role === 'student') {
    items.push({
      key: 'results',
      label: 'Посмотреть результаты',
      onSelect: () => navigate(`/admin/results/${user.id}`),
    });
  }
  return items;
}

function StudentsTable({
  schoolClass,
  onTransfer,
  onDetach,
}: {
  schoolClass: SchoolClass;
  onTransfer: (student: User) => void;
  onDetach: (student: User) => void;
}) {
  const navigate = useNavigate();

  if (schoolClass.students.length === 0) {
    return <div className="admin-empty">В классе пока нет учеников</div>;
  }

  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Ученик</th>
          <th>Email</th>
          <th>Статус</th>
          <th className="admin-table__actions-col" />
        </tr>
      </thead>
      <tbody>
        {schoolClass.students.map((s) => (
          <tr key={s.id}>
            <td>{s.full_name}</td>
            <td>{s.email}</td>
            <td>
              <span className={`status-dot ${s.is_active ? 'status-dot--on' : ''}`.trim()} />
              {s.is_active ? 'Активен' : 'Неактивен'}
            </td>
            <td className="admin-table__actions-col">
              <ActionMenu
                trigger={<Icon name="chevronDown" size={15} />}
                items={[
                  ...commonUserActions(s, navigate),
                  {
                    key: 'transfer',
                    label: 'Перевести в другой класс',
                    onSelect: () => onTransfer(s),
                  },
                  {
                    key: 'detach',
                    label: 'Открепить от класса',
                    danger: true,
                    onSelect: () => onDetach(s),
                  },
                ]}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TeachersTable({
  schoolClass,
  rows,
  showHomeroomColumn,
  onEditSubject,
  onToggleHomeroom,
  onDetach,
}: {
  schoolClass: SchoolClass;
  rows: TeacherInClass[];
  showHomeroomColumn: boolean;
  onEditSubject: (link: TeacherInClass) => void;
  onToggleHomeroom: (link: TeacherInClass) => Promise<void>;
  onDetach: (link: TeacherInClass) => void;
}) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  if (rows.length === 0) {
    return (
      <div className="admin-empty">
        {showHomeroomColumn
          ? 'К классу пока не привязан ни один учитель'
          : 'Классный руководитель не назначен'}
      </div>
    );
  }

  const toggle = async (link: TeacherInClass) => {
    setError(null);
    try {
      await onToggleHomeroom(link);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось изменить руководство');
    }
  };

  return (
    <>
      {error && <div className="form-error">{error}</div>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Учитель</th>
            <th>Email</th>
            <th>Предмет</th>
            {showHomeroomColumn && <th>Роль в классе</th>}
            <th className="admin-table__actions-col" />
          </tr>
        </thead>
        <tbody>
          {rows.map((link) => (
            <tr key={link.teacher.id}>
              <td>{link.teacher.full_name}</td>
              <td>{link.teacher.email}</td>
              <td>{link.subject ?? <span className="roster-cell--empty">не указан</span>}</td>
              {showHomeroomColumn && <td>{link.is_homeroom ? 'Кл. руководитель' : 'Предметник'}</td>}
              <td className="admin-table__actions-col">
                <ActionMenu
                  trigger={<Icon name="chevronDown" size={15} />}
                  items={[
                    ...commonUserActions(link.teacher, navigate),
                    {
                      key: 'subject',
                      label: link.subject ? 'Изменить предмет' : 'Указать предмет',
                      onSelect: () => onEditSubject(link),
                    },
                    {
                      key: 'homeroom',
                      label: link.is_homeroom
                        ? 'Снять классное руководство'
                        : 'Назначить классным руководителем',
                      onSelect: () => void toggle(link),
                    },
                    {
                      key: 'detach',
                      label: `Открепить от ${classLabel(schoolClass)}`,
                      danger: true,
                      onSelect: () => onDetach(link),
                    },
                  ]}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function studentsCountLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ученик`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ученика`;
  return `${n} учеников`;
}

function teachersCountLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} учитель`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} учителя`;
  return `${n} учителей`;
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
      if (homeroomId !== null) {
        // Кл. рук — это учитель класса с флагом, поэтому назначение и есть
        // привязка к классу: отдельного шага «добавить в учителя» не нужно.
        await assignTeachers(classId, [homeroomId], { isHomeroom: true });
      }
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
            <span>Классный руководитель (необязательно, можно добавить ещё позже)</span>
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


/**
 * Назначение в класс. Режим совпадает с активной вкладкой, поэтому кандидаты
 * и текст кнопки всегда соответствуют тому, что админ видит перед собой:
 *  students — ученики без класса (у ученика класс один);
 *  teachers — учителя, ещё не привязанные к ЭТОМУ классу (+ предмет на пачку);
 *  homeroom — учителя класса без флага и любые другие учителя школы: привязка
 *             и назначение руководителем делаются одним вызовом.
 */
function AssignModal({
  mode,
  schoolClass,
  allUsers,
  allClasses,
  onClose,
  onAssigned,
}: {
  mode: CompositionTab;
  schoolClass: SchoolClass;
  allUsers: User[];
  allClasses: SchoolClass[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [subject, setSubject] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const inThisClass = useMemo(
    () => new Map(schoolClass.teachers.map((t) => [t.teacher.id, t])),
    [schoolClass],
  );

  const candidates = useMemo(() => {
    // Неактивные не предлагаются вовсе: под этим флагом ходят и
    // деактивированные админом люди, и служебные респонденты архивного
    // импорта («Педагог 1 (архив…)», is_placeholder) — ни тех, ни других
    // назначать в живой класс нельзя.
    const active = allUsers.filter((u) => u.is_active);
    if (mode === 'students') {
      const assigned = new Set(allClasses.flatMap((c) => c.students.map((s) => s.id)));
      return active.filter((u) => u.role === 'student' && !assigned.has(u.id));
    }
    const teachers = active.filter((u) => u.role === 'teacher');
    if (mode === 'teachers') return teachers.filter((u) => !inThisClass.has(u.id));
    // homeroom: уже руководящих не предлагаем, остальных учителей школы — да
    return teachers.filter((u) => !inThisClass.get(u.id)?.is_homeroom);
  }, [mode, allUsers, allClasses, inThisClass]);

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
      if (mode === 'students') {
        await assignStudents(schoolClass.id, ids);
      } else if (mode === 'teachers') {
        await assignTeachers(schoolClass.id, ids, { subject: subject.trim() || null });
      } else {
        // Часть выбранных уже в классе — им нужен PATCH, остальных привязываем.
        // Иначе бэкенд ответит 409 «учитель уже прикреплён» на всю пачку.
        const existing = ids.filter((id) => inThisClass.has(id));
        const fresh = ids.filter((id) => !inThisClass.has(id));
        if (fresh.length > 0) await assignTeachers(schoolClass.id, fresh, { isHomeroom: true });
        for (const id of existing) {
          await updateTeacherInClass(schoolClass.id, id, { is_homeroom: true });
        }
      }
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить назначение');
    } finally {
      setSubmitting(false);
    }
  };

  const title = {
    students: `Ученики в класс ${classLabel(schoolClass)}`,
    teachers: `Учителя класса ${classLabel(schoolClass)}`,
    homeroom: `Классное руководство ${classLabel(schoolClass)}`,
  }[mode];

  const emptyText = {
    students: 'Свободных учеников нет — все уже распределены по классам',
    teachers: 'Все учителя уже ведут этот класс (или учителей нет вовсе)',
    homeroom: 'Все учителя школы уже руководят этим классом (или учителей нет вовсе)',
  }[mode];

  return (
    <Modal title={title} onClose={onClose}>
      {candidates.length === 0 ? (
        <div className="admin-empty">{emptyText}</div>
      ) : (
        <>
          {mode === 'teachers' && (
            <label className="form-field">
              <span>Предмет (необязательно, общий для выбранных)</span>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="литература"
                maxLength={100}
              />
            </label>
          )}
          <div className="assign-list">
            {candidates.map((u) => (
              <label key={u.id} className="assign-item">
                <input type="checkbox" checked={checked.has(u.id)} onChange={() => toggle(u.id)} />
                <span className="assign-item__name">{u.full_name}</span>
                <span className="assign-item__email">
                  {mode === 'homeroom' && inThisClass.has(u.id)
                    ? 'уже учитель класса'
                    : u.email}
                </span>
              </label>
            ))}
          </div>
        </>
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

/** Правка предмета одного учителя в одном классе. */
function SubjectModal({
  schoolClass,
  link,
  onClose,
  onSaved,
}: {
  schoolClass: SchoolClass;
  link: TeacherInClass;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [subject, setSubject] = useState(link.subject ?? '');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Пустая строка — это «стереть предмет», отправляем null: бэкенд
      // различает отсутствие ключа и явный null.
      await updateTeacherInClass(schoolClass.id, link.teacher.id, {
        subject: subject.trim() || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить предмет');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Предмет · ${link.teacher.full_name}`} onClose={onClose}>
      <label className="form-field">
        <span>Что ведёт в классе {classLabel(schoolClass)}</span>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="литература"
          maxLength={100}
          autoFocus
        />
      </label>
      <p className="roster-hint">
        Предмет относится только к этому классу — в другом классе у того же учителя он свой.
      </p>

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'Сохраняем…' : 'Сохранить'}
        </Button>
      </div>
    </Modal>
  );
}

/**
 * Перевод ученика в другой класс. Отдельного эндпоинта нет и не нужно: класс
 * у ученика один, поэтому привязка к новому просто перезаписывает старый.
 */
function TransferModal({
  student,
  from,
  allClasses,
  onClose,
  onTransferred,
}: {
  student: User;
  from: SchoolClass;
  allClasses: SchoolClass[];
  onClose: () => void;
  onTransferred: () => void;
}) {
  const targets = useMemo(() => allClasses.filter((c) => c.id !== from.id), [allClasses, from.id]);
  const [targetId, setTargetId] = useState<number | null>(targets[0]?.id ?? null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (targetId === null) return;
    setError(null);
    setSubmitting(true);
    try {
      await assignStudents(targetId, [student.id]);
      onTransferred();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось перевести ученика');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Перевод · ${student.full_name}`} onClose={onClose}>
      {targets.length === 0 ? (
        <div className="admin-empty">Других классов пока нет — переводить некуда</div>
      ) : (
        <label className="form-field">
          <span>Из {classLabel(from)} в класс</span>
          <select
            value={targetId ?? ''}
            onChange={(e) => setTargetId(Number(e.target.value))}
            autoFocus
          >
            {targets.map((c) => (
              <option key={c.id} value={c.id}>
                {classLabel(c)}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="roster-hint">
        Уже собранные результаты останутся за прежним классом: анкеты хранят класс на момент
        кампании.
      </p>

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting || targetId === null}>
          {submitting ? 'Переводим…' : 'Перевести'}
        </Button>
      </div>
    </Modal>
  );
}

/** Подтверждение открепления — действие видимое, но обратимое: не удаление. */
function DetachModal({
  target,
  onClose,
  onDetached,
}: {
  target: DetachTarget;
  onClose: () => void;
  onDetached: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      if (target.kind === 'student') {
        await removeStudentFromClass(target.schoolClass.id, target.user.id);
      } else {
        await removeTeacherFromClass(target.schoolClass.id, target.user.id);
      }
      onDetached();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось открепить');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Открепить от класса" onClose={onClose}>
      <p className="roster-hint">
        {target.user.full_name} будет откреплён от класса {classLabel(target.schoolClass)}.
        Пользователь останется в системе со всей историей — при необходимости его можно привязать
        обратно.
        {target.kind === 'teacher' && ' Классное руководство, если оно было, тоже снимется.'}
      </p>

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'Открепляем…' : 'Открепить'}
        </Button>
      </div>
    </Modal>
  );
}
