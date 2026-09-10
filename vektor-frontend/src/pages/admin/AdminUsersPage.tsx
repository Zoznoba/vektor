import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Icon } from '../../components/icons/Icon';
import { ActionMenu } from '../../components/ui/ActionMenu';
import type { ActionMenuItem } from '../../components/ui/ActionMenu';
import { SelectAllCheckbox, SelectionBar } from '../../components/ui/SelectionBar';
import { useApi } from '../../hooks/useApi';
import { useRowSelection } from '../../hooks/useRowSelection';
import {
  fetchUsers,
  createUser,
  bulkCreateUsers,
  assignChildren,
  setUserActive,
  resetPassword,
} from '../../api/users';
import type { BulkUserIn } from '../../api/users';
import { fetchClasses } from '../../api/classes';
import { fetchCases, assignCaseStudents, assignCaseTeachers } from '../../api/cases';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_BADGE, ROLE_LABELS } from '../../types/auth';
import type { User, UserRole } from '../../types/auth';
import { classLabel } from '../../types/school';
import type { SchoolClass } from '../../types/school';
import type { Case } from '../../types/case';
import { parseRoster, rosterErrorCount } from './roster';
import { RosterInput } from './RosterInput';
import './admin.css';

type RoleFilter = UserRole | 'all';
// «Неактивен» в этой системе — единственная форма удаления (7l): вход
// заблокирован, история цела. Таких набирается больше, чем действующих людей
// (выпускники прошлых лет), поэтому по умолчанию список показывает активных, а
// выбывшие достаются отдельным режимом, а не тонут в общей таблице.
type StatusFilter = 'active' | 'inactive' | 'all';

/** Колонка сортировки таблицы пользователей. */
type SortKey = 'name' | 'email' | 'role' | 'class' | 'case' | 'status';
type SortDir = 'asc' | 'desc';

const ROLE_ORDER: Record<UserRole, number> = { admin: 0, teacher: 1, parent: 2, student: 3 };

/** Массовое действие над выделенными строками. */
type BulkAction = 'case' | 'parent' | 'deactivate';

/** id пользователя → метка класса(ов): ученику — его класс, учителю — список. */
function buildClassIndex(classes: SchoolClass[] | null): Map<number, string> {
  const index = new Map<number, string>();
  if (!classes) return index;
  for (const cls of classes) {
    const label = classLabel(cls);
    for (const s of cls.students) index.set(s.id, label);
    for (const { teacher } of cls.teachers) {
      index.set(teacher.id, index.has(teacher.id) ? `${index.get(teacher.id)}, ${label}` : label);
    }
  }
  return index;
}

/** id пользователя → название его кейса. Кейс ровно один и у ученика, и у
 *  учителя (FK users.case_id), поэтому склеивать названия, как у классов, не
 *  требуется. */
function buildCaseIndex(cases: Case[] | null): Map<number, string> {
  const index = new Map<number, string>();
  if (!cases) return index;
  for (const kase of cases) {
    for (const member of [...kase.students, ...kase.teachers]) index.set(member.id, kase.name);
  }
  return index;
}

function peopleCountLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} человека`;
  return `${n} человек`;
}

/**
 * «Пользователи» — единый список людей школы.
 *
 * Устроен как состав класса в AdminClassesPage: таблица, чекбоксы,
 * `SelectionBar` с массовыми действиями и дропдаун контекстных действий в
 * конце строки. Раскрывающейся панели «Действия» над таблицей больше нет:
 * она сдвигала таблицу вниз (выбранная строка могла уехать за экран) и мешала
 * в себе три разные вещи — карточку человека, пульт действий и список детей.
 * Всё это переехало на страницу пользователя (`/admin/users/:id`), а клик по
 * строке ведёт туда.
 *
 * Верх экрана НЕ копирует сетку карточек классов/кейсов сознательно: там
 * карточка — сущность со своим составом, здесь роль — всего лишь фильтр,
 * и чипсы описывают её честнее.
 */
export function AdminUsersPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user: currentUser } = useAuth();
  const users = useApi(fetchUsers);
  const classes = useApi(fetchClasses);
  const cases = useApi(fetchCases);

  // Приход со «Сводки» по клику на тайл — сразу с нужным фильтром роли.
  const initialRoleFilter =
    (location.state as { roleFilter?: RoleFilter } | null)?.roleFilter ?? 'all';
  const [roleFilter, setRoleFilter] = useState<RoleFilter>(initialRoleFilter);
  const [classFilter, setClassFilter] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active');
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [showCreate, setShowCreate] = useState(false);
  const [showBulkCreate, setShowBulkCreate] = useState(false);
  const [bulkAction, setBulkAction] = useState<BulkAction | null>(null);
  const [resetPasswordFor, setResetPasswordFor] = useState<User | null>(null);
  // Деактивация одного из дропдауна строки и пачки из выделения — путь общий,
  // как у открепления в «Классах»: одна модалка, на входе список.
  const [deactivating, setDeactivating] = useState<User[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const classIndex = useMemo(() => buildClassIndex(classes.data), [classes.data]);
  const caseIndex = useMemo(() => buildCaseIndex(cases.data), [cases.data]);

  const allUsers = useMemo(() => users.data ?? [], [users.data]);

  // Возврат со страницы пользователя по прямой ссылке подсвечивает строку, с
  // которой всё началось (state кладут «Классы», «Кейсы» и сам профиль).
  const highlightedId = (location.state as { userId?: number } | null)?.userId ?? null;

  // Фильтр по классу считаем по составу класса (ученики + учителя), а не по
  // колонке-подписи: подпись у учителя склеена из нескольких классов и на
  // подстроку не проверяется.
  // Статус входит в scoped, а не в filtered: счётчики на чипсах ролей должны
  // считать то же, что лежит в таблице, иначе «Ученики · 159» над списком из
  // 138 действующих читается как ошибка — та же причина, что у класса ниже.
  const scoped = useMemo(() => {
    const byStatus =
      statusFilter === 'all'
        ? allUsers
        : allUsers.filter((u) => u.is_active === (statusFilter === 'active'));
    if (classFilter === null) return byStatus;
    const cls = (classes.data ?? []).find((c) => c.id === classFilter);
    if (!cls) return byStatus;
    const members = new Set<number>([
      ...cls.students.map((s) => s.id),
      ...cls.teachers.map((t) => t.teacher.id),
    ]);
    return byStatus.filter((u) => members.has(u.id));
  }, [allUsers, classes.data, classFilter, statusFilter]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return scoped.filter((u) => {
      if (roleFilter !== 'all' && u.role !== roleFilter) return false;
      if (!query) return true;
      return u.full_name.toLowerCase().includes(query) || u.email.toLowerCase().includes(query);
    });
  }, [scoped, roleFilter, search]);

  // Счётчики на чипсах — в пределах выбранного класса, а не по всей школе:
  // иначе «Ученики · 136» рядом с таблицей из тринадцати читается как ошибка.
  const countByRole = useMemo(() => {
    const counts: Record<RoleFilter, number> = {
      all: scoped.length,
      student: 0,
      teacher: 0,
      parent: 0,
      admin: 0,
    };
    for (const u of scoped) counts[u.role] += 1;
    return counts;
  }, [scoped]);

  // Сортировка — поверх фильтра, целиком на клиенте: список уже весь в памяти.
  const sorted = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1;
    const value = (u: User): string | number => {
      switch (sortKey) {
        case 'name':
          return u.full_name.toLowerCase();
        case 'email':
          return u.email.toLowerCase();
        case 'role':
          return ROLE_ORDER[u.role];
        case 'class':
          return classIndex.get(u.id) ?? '￿';
        case 'case':
          return caseIndex.get(u.id) ?? '￿';
        case 'status':
          return u.is_active ? 0 : 1;
      }
    };
    return [...filtered].sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      if (av < bv) return -dir;
      if (av > bv) return dir;
      return a.full_name.toLowerCase().localeCompare(b.full_name.toLowerCase(), 'ru');
    });
  }, [filtered, sortKey, sortDir, classIndex, caseIndex]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const rowIds = useMemo(() => sorted.map((u) => u.id), [sorted]);
  // resetKey — все фильтры разом: выделение не должно переживать смену
  // выборки, иначе массовое действие уедет на людей, которых на экране нет.
  const selection = useRowSelection(
    rowIds,
    `${roleFilter}:${classFilter ?? 'all'}:${statusFilter}:${search.trim().toLowerCase()}`,
  );
  const selectedUsers = useMemo(
    () => sorted.filter((u) => selection.selectedIds.includes(u.id)),
    [sorted, selection.selectedIds],
  );

  // Что можно делать с выделением, зависит от его состава — кнопки не
  // прячем, а гасим с подсказкой: исчезающая кнопка читается как поломка.
  const caseEligible = selectedUsers.every((u) => u.role === 'student' || u.role === 'teacher');
  const parentEligible =
    selectedUsers.length > 0 && selectedUsers.every((u) => u.role === 'student');
  const selectionHasSelf = selectedUsers.some((u) => u.id === currentUser?.id);

  const filters: { key: RoleFilter; label: string }[] = [
    { key: 'all', label: 'Все' },
    { key: 'student', label: 'Ученики' },
    { key: 'teacher', label: 'Учителя' },
    { key: 'parent', label: 'Родители' },
    { key: 'admin', label: 'Админ' },
  ];

  const handleActivate = async (user: User) => {
    setActionError(null);
    try {
      await setUserActive(user.id, true);
      users.reload();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : 'Не удалось активировать пользователя',
      );
    }
  };

  const rowActions = (user: User): ActionMenuItem[] => {
    const items: ActionMenuItem[] = [
      {
        key: 'profile',
        label: 'Открыть профиль',
        onSelect: () => navigate(`/admin/users/${user.id}`),
      },
    ];
    items.push({
      key: 'password',
      label: 'Сбросить пароль',
      onSelect: () => setResetPasswordFor(user),
    });
    if (user.is_active) {
      items.push({
        key: 'deactivate',
        label: 'Деактивировать',
        danger: true,
        disabled: user.id === currentUser?.id,
        onSelect: () => setDeactivating([user]),
      });
    } else {
      items.push({
        key: 'activate',
        label: 'Активировать',
        onSelect: () => void handleActivate(user),
      });
    }
    return items;
  };

  return (
    <AdminShell activeNavKey="users">
      <div className="admin-toolbar">
        <h2>Пользователи</h2>
        <div className="filter-chips">
          {filters.map((f) => (
            <button
              key={f.key}
              className={`filter-chip ${roleFilter === f.key ? 'filter-chip--active' : ''}`.trim()}
              onClick={() => setRoleFilter(f.key)}
            >
              {f.label} · {countByRole[f.key]}
            </button>
          ))}
        </div>
        <div className="admin-toolbar__spacer" />
        <select
          className="admin-select"
          value={classFilter ?? ''}
          onChange={(e) => setClassFilter(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Все классы</option>
          {(classes.data ?? []).map((cls) => (
            <option key={cls.id} value={cls.id}>
              {classLabel(cls)}
            </option>
          ))}
        </select>
        <select
          className="admin-select"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          <option value="active">Активные</option>
          <option value="inactive">Неактивные</option>
          <option value="all">Все статусы</option>
        </select>
        {/* Поиск и «+» — одна неразрывная группа: тулбар переносится по
            словам, и в одиночку кнопка уехала бы на новую строку к левому
            краю, а меню (оно раскрывается влево от правого края кнопки) —
            за границу экрана. Рядом с поиском слева от неё всегда есть
            место под меню. */}
        <div className="admin-toolbar__group">
          <div className="search-box">
            <Icon name="search" size={16} />
            <input
              type="search"
              placeholder="Поиск по имени или email"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {/* Одна кнопка с выбором вместо двух рядом: «Добавить» и «Пачкой»
              стояли как равные, хотя это один и тот же поступок в двух
              масштабах — и вдвоём переносили тулбар на вторую строку.
              Только «+», без подписи: с ней ряд снова уезжал на вторую
              строку, а меню — за левую границу экрана. Пункты по одному
              слову и без глагола — они читаются как продолжение подсказки
              кнопки («Добавить…»), а «ФИО ⇥ email, можно скопировать из
              Excel» и так стоит первой строкой внутри самой модалки. */}
          <ActionMenu
            triggerClassName="btn btn-primary btn-icon"
            triggerLabel="Добавить пользователей"
            trigger={<Icon name="plus" size={16} />}
            items={[
              {
                key: 'one',
                label: 'Одного',
                onSelect: () => setShowCreate(true),
              },
              {
                key: 'many',
                label: 'Списком',
                onSelect: () => setShowBulkCreate(true),
              },
            ]}
          />
        </div>
      </div>

      {users.error && <div className="form-error">{users.error}</div>}
      {actionError && <div className="form-error">{actionError}</div>}

      <Panel className="admin-table-panel">
        <SelectionBar selection={selection} itemLabel={peopleCountLabel}>
          <Button
            variant="secondary"
            disabled={!caseEligible}
            title={caseEligible ? undefined : 'В кейс можно добавить только учеников и учителей'}
            onClick={() => setBulkAction('case')}
          >
            Добавить в кейс
          </Button>
          <Button
            variant="secondary"
            disabled={!parentEligible}
            title={parentEligible ? undefined : 'Привязать к родителю можно только учеников'}
            onClick={() => setBulkAction('parent')}
          >
            Привязать к родителю
          </Button>
          <Button
            variant="danger"
            disabled={selectionHasSelf}
            title={selectionHasSelf ? 'В выделении ваша собственная учётная запись' : undefined}
            onClick={() => setDeactivating(selectedUsers)}
          >
            Деактивировать
          </Button>
        </SelectionBar>

        {users.loading && !users.data ? (
          <div className="admin-empty">Загрузка…</div>
        ) : sorted.length === 0 ? (
          <div className="admin-empty">Никого не нашлось</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th className="admin-table__select-col">
                  <SelectAllCheckbox selection={selection} />
                </th>
                <SortableTh label="Имя" col="name" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortableTh label="Email" col="email" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortableTh label="Роль" col="role" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortableTh label="Класс" col="class" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortableTh label="Кейс" col="case" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <SortableTh label="Статус" col="status" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                <th className="admin-table__actions-col" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((u) => (
                <tr
                  key={u.id}
                  className={u.id === highlightedId ? 'admin-table__row--selected' : ''}
                  onClick={() => {
                    if (window.getSelection()?.toString()) return;
                    navigate(`/admin/users/${u.id}`);
                  }}
                >
                  <td
                    className="admin-table__select-col"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      aria-label={`Выбрать: ${u.full_name}`}
                      checked={selection.has(u.id)}
                      onChange={() => selection.toggle(u.id)}
                    />
                  </td>
                  <td>{u.full_name}</td>
                  <td>{u.email}</td>
                  <td>
                    <Badge variant={ROLE_BADGE[u.role]}>{ROLE_LABELS[u.role]}</Badge>
                  </td>
                  <td>{classIndex.get(u.id) ?? '—'}</td>
                  <td>{caseIndex.get(u.id) ?? '—'}</td>
                  <td>
                    <span className={`status-dot ${u.is_active ? 'status-dot--on' : ''}`.trim()} />
                    {u.is_active ? 'Активен' : 'Неактивен'}
                  </td>
                  <td className="admin-table__actions-col">
                    <ActionMenu
                      trigger={<Icon name="chevronDown" size={15} />}
                      items={rowActions(u)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            users.reload();
          }}
        />
      )}

      {showBulkCreate && (
        <BulkCreateUsersModal
          allUsers={allUsers}
          classes={classes.data ?? []}
          cases={cases.data ?? []}
          onClose={() => setShowBulkCreate(false)}
          onCreated={() => {
            setShowBulkCreate(false);
            users.reload();
            classes.reload();
            cases.reload();
          }}
        />
      )}

      {bulkAction === 'case' && (
        <AssignToCaseModal
          users={selectedUsers}
          cases={cases.data ?? []}
          onClose={() => setBulkAction(null)}
          onAssigned={() => {
            setBulkAction(null);
            selection.clear();
            users.reload();
            cases.reload();
          }}
        />
      )}

      {bulkAction === 'parent' && (
        <AssignToParentModal
          students={selectedUsers}
          parents={allUsers.filter((u) => u.role === 'parent' && u.is_active)}
          onClose={() => setBulkAction(null)}
          onAssigned={() => {
            setBulkAction(null);
            selection.clear();
          }}
        />
      )}

      {deactivating && (
        <DeactivateModal
          users={deactivating}
          onClose={() => setDeactivating(null)}
          onDone={() => {
            setDeactivating(null);
            selection.clear();
            users.reload();
          }}
        />
      )}

      {resetPasswordFor && (
        <ResetPasswordModal
          user={resetPasswordFor}
          onClose={() => setResetPasswordFor(null)}
        />
      )}
    </AdminShell>
  );
}

function SortableTh({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
}: {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const active = sortKey === col;
  return (
    <th
      className={`admin-table__sortable ${active ? 'admin-table__sortable--active' : ''}`.trim()}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={() => onSort(col)}
    >
      {label}
      <span className="admin-table__sort-caret">{active ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}</span>
    </th>
  );
}

function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('student');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await createUser({
        email: email.trim(),
        password,
        full_name: fullName.trim(),
        role,
      });
      onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Пользователь с таким email уже существует');
      } else if (err instanceof ApiError && err.status === 422) {
        setError('Проверьте поля: пароль от 8 символов, корректный email');
      } else {
        setError(err instanceof ApiError ? err.message : 'Не удалось создать пользователя');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Новый пользователь" onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate>
        <label className="form-field">
          <span>Имя и фамилия</span>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </label>
        <label className="form-field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="имя@shkola-vektor.ru"
            required
          />
        </label>
        <label className="form-field">
          <span>Пароль</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Минимум 8 символов"
            required
          />
        </label>
        <label className="form-field">
          <span>Роль</span>
          <select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
            <option value="student">Ученик</option>
            <option value="teacher">Учитель</option>
            <option value="parent">Родитель</option>
            <option value="admin">Администратор</option>
          </select>
        </label>

        {error && <div className="form-error">{error}</div>}

        <div className="modal__actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Создаём…' : 'Создать'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * Массовое заведение людей из вставленного списка. Тот же `/users/bulk`, что
 * в мастере «Новый класс», но без самого класса: роль общая на пачку, а
 * привязка к классу/кейсу — необязательная и делается тем же вызовом.
 *
 * Класс предлагаем только для учеников (бэкенд привязывает по class_id именно
 * их), кейс — ученикам и учителям: членство в кейсе одно на обе роли.
 */
function BulkCreateUsersModal({
  allUsers,
  classes,
  cases,
  onClose,
  onCreated,
}: {
  allUsers: User[];
  classes: SchoolClass[];
  cases: Case[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [role, setRole] = useState<UserRole>('student');
  const [classId, setClassId] = useState<number | null>(null);
  const [caseId, setCaseId] = useState<number | null>(null);
  const [roster, setRoster] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const existingEmails = useMemo(
    () => new Set(allUsers.map((u) => u.email.toLowerCase())),
    [allUsers],
  );
  const rows = useMemo(() => parseRoster(roster, existingEmails), [roster, existingEmails]);
  const errorCount = rosterErrorCount(rows);
  const canSubmit = rows.length > 0 && errorCount === 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      const users: BulkUserIn[] = rows.map((r) => ({
        email: r.email,
        full_name: r.fullName,
        role,
      }));
      await bulkCreateUsers(
        users,
        role === 'student' ? classId : null,
        role === 'student' || role === 'teacher' ? caseId : null,
      );
      onCreated();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Некоторые email уже заняты — поправьте список и попробуйте снова');
      } else if (err instanceof ApiError && err.status === 422) {
        // Бэк (Pydantic EmailStr) строже нашего превью: режет зарезервированные
        // домены (.test, example.com), которые формально «похожи» на email.
        setError(
          'Бэкенд отклонил один из адресов как недопустимый email — обычно это ' +
            'зарезервированный домен вроде «@test.test» или «@example.com». ' +
            'Используйте реальный домен и попробуйте снова.',
        );
      } else {
        setError(err instanceof ApiError ? err.message : 'Не удалось завести пользователей');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Добавить пачкой" onClose={onClose}>
      <label className="form-field">
        <span>Роль (общая на всю пачку)</span>
        <select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
          <option value="student">Ученики</option>
          <option value="teacher">Учителя</option>
          <option value="parent">Родители</option>
        </select>
      </label>

      {role === 'student' && (
        <label className="form-field">
          <span>Сразу в класс (необязательно)</span>
          <select
            value={classId ?? ''}
            onChange={(e) => setClassId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— не привязывать —</option>
            {classes.map((cls) => (
              <option key={cls.id} value={cls.id}>
                {classLabel(cls)}
              </option>
            ))}
          </select>
        </label>
      )}

      {(role === 'student' || role === 'teacher') && (
        <label className="form-field">
          <span>Сразу в кейс (необязательно)</span>
          <select
            value={caseId ?? ''}
            onChange={(e) => setCaseId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— не привязывать —</option>
            {cases.map((kase) => (
              <option key={kase.id} value={kase.id}>
                {kase.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <RosterInput value={roster} onChange={setRoster} rows={rows} errorCount={errorCount} />

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting || !canSubmit}>
          {submitting ? 'Создаём…' : `Создать ${rows.length}`}
        </Button>
      </div>
    </Modal>
  );
}

/**
 * Массовое добавление в кейс. Ученики и учителя уходят разными ручками
 * (у бэкенда их две), но одним действием админа.
 *
 * Уже состоящих в каком-либо кейсе отфильтровываем ЗДЕСЬ: членство одно, и
 * бэкенд отвечает на чужого участника 409 — на всю пачку. Перевод между
 * кейсами делается явно, через открепление в «Кейсах».
 */
function AssignToCaseModal({
  users,
  cases,
  onClose,
  onAssigned,
}: {
  users: User[];
  cases: Case[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [caseId, setCaseId] = useState<number | null>(cases[0]?.id ?? null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const inSomeCase = useMemo(() => {
    const ids = new Set<number>();
    for (const kase of cases) {
      for (const m of [...kase.students, ...kase.teachers]) ids.add(m.id);
    }
    return ids;
  }, [cases]);

  const free = users.filter((u) => !inSomeCase.has(u.id));
  const skipped = users.length - free.length;
  const students = free.filter((u) => u.role === 'student').map((u) => u.id);
  const teachers = free.filter((u) => u.role === 'teacher').map((u) => u.id);

  const handleSubmit = async () => {
    if (caseId === null || free.length === 0) return;
    setError(null);
    setSubmitting(true);
    try {
      if (students.length > 0) await assignCaseStudents(caseId, students);
      if (teachers.length > 0) await assignCaseTeachers(caseId, teachers);
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось добавить в кейс');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Добавить в кейс" onClose={onClose}>
      {cases.length === 0 ? (
        <div className="admin-empty">Кейсов пока нет — создайте кейс в разделе «Кейсы»</div>
      ) : (
        <>
          <label className="form-field">
            <span>Кейс</span>
            <select
              value={caseId ?? ''}
              onChange={(e) => setCaseId(e.target.value ? Number(e.target.value) : null)}
            >
              {cases.map((kase) => (
                <option key={kase.id} value={kase.id}>
                  {kase.name}
                </option>
              ))}
            </select>
          </label>

          <p>
            Будут добавлены: {students.length > 0 && `учеников — ${students.length}`}
            {students.length > 0 && teachers.length > 0 && ', '}
            {teachers.length > 0 && `учителей — ${teachers.length}`}
            {free.length === 0 && 'никто'}.
          </p>
          {skipped > 0 && (
            <p className="roster-hint">
              Пропущено: {skipped} — эти люди уже состоят в другом кейсе. Членство в кейсе одно,
              перевод делается через открепление в разделе «Кейсы».
            </p>
          )}

          <div className="detach-list">
            <ul>
              {free.map((u) => (
                <li key={u.id}>
                  {u.full_name} — {ROLE_LABELS[u.role]}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting || caseId === null || free.length === 0}>
          {submitting ? 'Добавляем…' : `Добавить (${free.length})`}
        </Button>
      </div>
    </Modal>
  );
}

/**
 * Массовая привязка выделенных учеников к одному родителю. Один вызов
 * `assignChildren` на всю пачку, повторная привязка на бэкенде идемпотентна —
 * поэтому уже привязанных детей отдельно не отсеиваем.
 */
function AssignToParentModal({
  students,
  parents,
  onClose,
  onAssigned,
}: {
  students: User[];
  parents: User[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [parentId, setParentId] = useState<number | null>(parents[0]?.id ?? null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return parents;
    return parents.filter(
      (p) => p.full_name.toLowerCase().includes(query) || p.email.toLowerCase().includes(query),
    );
  }, [parents, search]);

  const handleSubmit = async () => {
    if (parentId === null) return;
    setError(null);
    setSubmitting(true);
    try {
      await assignChildren(
        parentId,
        students.map((s) => s.id),
      );
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось привязать детей');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Привязать к родителю" onClose={onClose}>
      <p>
        Выбранные ученики ({students.length}) станут детьми одного родителя:{' '}
        {students.map((s) => s.full_name).join(', ')}.
      </p>

      {parents.length === 0 ? (
        <div className="admin-empty">Активных родителей в школе пока нет</div>
      ) : (
        <>
          <div className="search-box search-box--block">
            <Icon name="search" size={16} />
            <input
              type="search"
              placeholder="Поиск родителя"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="assign-list">
            {visible.map((p) => (
              <label key={p.id} className="assign-item">
                <input
                  type="radio"
                  name="parent"
                  checked={parentId === p.id}
                  onChange={() => setParentId(p.id)}
                />
                <span className="assign-item__name">{p.full_name}</span>
                <span className="assign-item__email">{p.email}</span>
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
        <Button onClick={handleSubmit} disabled={submitting || parentId === null}>
          {submitting ? 'Привязываем…' : 'Привязать'}
        </Button>
      </div>
    </Modal>
  );
}

/**
 * Деактивация одного или сразу нескольких.
 *
 * Массового эндпоинта у бэкенда нет, поэтому шлём по одному запросу на
 * человека и честно показываем, кто не прошёл: молчаливый «успех» после
 * половины упавших запросов хуже, чем список ошибок.
 */
export function DeactivateModal({
  users,
  onClose,
  onDone,
}: {
  users: User[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [failed, setFailed] = useState<string[] | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleConfirm = async () => {
    setFailed(null);
    setSubmitting(true);
    const errors: string[] = [];
    for (const user of users) {
      try {
        await setUserActive(user.id, false);
      } catch (err) {
        errors.push(
          `${user.full_name}: ${err instanceof ApiError ? err.message : 'неизвестная ошибка'}`,
        );
      }
    }
    setSubmitting(false);
    if (errors.length === 0) onDone();
    else setFailed(errors);
  };

  return (
    <Modal
      title={users.length === 1 ? 'Деактивировать пользователя' : 'Деактивировать пользователей'}
      onClose={onClose}
    >
      <p>
        {users.length === 1 ? users[0].full_name : `Выбранные (${users.length})`} потеряют доступ
        к системе: вход будет заблокирован. История (ответы анкет, привязки к классу или детям)
        сохранится, действие можно отменить в любой момент кнопкой «Активировать».
      </p>

      {users.length > 1 && (
        <div className="detach-list">
          <ul>
            {users.map((u) => (
              <li key={u.id}>{u.full_name}</li>
            ))}
          </ul>
        </div>
      )}

      {failed && (
        <div className="form-error">
          Не удалось деактивировать: {failed.join('; ')}. Остальные деактивированы.
        </div>
      )}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={failed ? onDone : onClose}>
          {failed ? 'Закрыть' : 'Отмена'}
        </Button>
        <Button variant="danger" onClick={handleConfirm} disabled={submitting}>
          {submitting ? 'Деактивируем…' : 'Деактивировать'}
        </Button>
      </div>
    </Modal>
  );
}

export function ResetPasswordModal({ user, onClose }: { user: User; onClose: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [newPassword, setNewPassword] = useState<string | null>(null);

  const handleConfirm = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const result = await resetPassword(user.id);
      setNewPassword(result.new_password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сбросить пароль');
    } finally {
      setSubmitting(false);
    }
  };

  if (newPassword) {
    return (
      <Modal title="Пароль сброшен" onClose={onClose}>
        <p>
          Новый пароль для {user.full_name} — передайте его прямо сейчас: повторно показать
          нельзя, только сбросить ещё раз.
        </p>
        <div className="password-reveal">{newPassword}</div>
        <div className="modal__actions">
          <Button onClick={onClose}>Готово</Button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Сбросить пароль" onClose={onClose}>
      <p>
        {user.full_name} больше не сможет войти со старым паролем. Новый пароль будет показан
        один раз сразу после сброса — почтовой рассылки в системе пока нет.
      </p>

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button variant="danger" onClick={handleConfirm} disabled={submitting}>
          {submitting ? 'Сбрасываем…' : 'Сбросить пароль'}
        </Button>
      </div>
    </Modal>
  );
}
