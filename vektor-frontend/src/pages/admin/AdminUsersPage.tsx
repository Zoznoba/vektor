import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Avatar } from '../../components/ui/Avatar';
import { Modal } from '../../components/ui/Modal';
import { Icon } from '../../components/icons/Icon';
import { useApi } from '../../hooks/useApi';
import { fetchUsers, createUser, fetchChildren, assignChildren } from '../../api/users';
import { fetchClasses } from '../../api/classes';
import { ApiError } from '../../api/client';
import { ROLE_LABELS } from '../../types/auth';
import type { User, UserRole } from '../../types/auth';
import { classLabel } from '../../types/school';
import type { SchoolClass } from '../../types/school';
import './admin.css';

type RoleFilter = UserRole | 'all';

const ROLE_BADGE: Record<UserRole, 'sage' | 'blue' | 'gray'> = {
  student: 'sage',
  teacher: 'blue',
  parent: 'gray',
  admin: 'gray',
};

/** id пользователя → метка класса(ов): ученику — его класс, учителю — список. */
function buildClassIndex(classes: SchoolClass[] | null): Map<number, string> {
  const index = new Map<number, string>();
  if (!classes) return index;
  for (const cls of classes) {
    const label = classLabel(cls);
    for (const s of cls.students) index.set(s.id, label);
    for (const t of cls.teachers) {
      index.set(t.id, index.has(t.id) ? `${index.get(t.id)}, ${label}` : label);
    }
  }
  return index;
}

export function AdminUsersPage() {
  const users = useApi(fetchUsers);
  const classes = useApi(fetchClasses);

  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const classIndex = useMemo(() => buildClassIndex(classes.data), [classes.data]);

  const allUsers = useMemo(() => users.data ?? [], [users.data]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return allUsers.filter((u) => {
      if (roleFilter !== 'all' && u.role !== roleFilter) return false;
      if (!query) return true;
      return u.full_name.toLowerCase().includes(query) || u.email.toLowerCase().includes(query);
    });
  }, [allUsers, roleFilter, search]);

  const countByRole = useMemo(() => {
    const counts: Record<RoleFilter, number> = {
      all: allUsers.length,
      student: 0,
      teacher: 0,
      parent: 0,
      admin: 0,
    };
    for (const u of allUsers) counts[u.role] += 1;
    return counts;
  }, [allUsers]);

  const selected = allUsers.find((u) => u.id === selectedId) ?? null;

  const filters: { key: RoleFilter; label: string }[] = [
    { key: 'all', label: 'Все' },
    { key: 'student', label: 'Ученики' },
    { key: 'teacher', label: 'Учителя' },
    { key: 'parent', label: 'Родители' },
    { key: 'admin', label: 'Админ' },
  ];

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
        <div className="search-box">
          <Icon name="search" size={16} />
          <input
            type="search"
            placeholder="Поиск по имени или email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Icon name="plus" size={15} />
          Добавить
        </Button>
      </div>

      {users.error && <div className="form-error">{users.error}</div>}

      <Panel className="admin-table-panel">
        {users.loading ? (
          <div className="admin-empty">Загрузка…</div>
        ) : filtered.length === 0 ? (
          <div className="admin-empty">Никого не нашлось</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Email</th>
                <th>Роль</th>
                <th>Класс</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr
                  key={u.id}
                  className={u.id === selectedId ? 'admin-table__row--selected' : ''}
                  onClick={() => setSelectedId(u.id === selectedId ? null : u.id)}
                >
                  <td>{u.full_name}</td>
                  <td>{u.email}</td>
                  <td>
                    <Badge variant={ROLE_BADGE[u.role]}>{ROLE_LABELS[u.role]}</Badge>
                  </td>
                  <td>{classIndex.get(u.id) ?? '—'}</td>
                  <td>
                    <span
                      className={`status-dot ${u.is_active ? 'status-dot--on' : ''}`.trim()}
                    />
                    {u.is_active ? 'Активен' : 'Неактивен'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {selected && (
        <Panel title="Карточка пользователя">
          <div className="user-card">
            <Avatar fullName={selected.full_name} className="user-card__avatar" />
            <div className="user-card__main">
              <div className="user-card__name">{selected.full_name}</div>
              <Badge variant={ROLE_BADGE[selected.role]}>{ROLE_LABELS[selected.role]}</Badge>
            </div>
          </div>
          <div className="profile-rows">
            <div className="profile-row">
              <span>Email</span>
              <span>{selected.email}</span>
            </div>
            <div className="profile-row">
              <span>Класс</span>
              <span>{classIndex.get(selected.id) ?? '—'}</span>
            </div>
            <div className="profile-row">
              <span>Статус</span>
              <span>{selected.is_active ? 'Активен' : 'Неактивен'}</span>
            </div>
          </div>
          {selected.role === 'parent' && (
            <ParentChildrenSection key={selected.id} parent={selected} allUsers={allUsers} />
          )}
        </Panel>
      )}

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            users.reload();
          }}
        />
      )}
    </AdminShell>
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

function ParentChildrenSection({ parent, allUsers }: { parent: User; allUsers: User[] }) {
  const [children, setChildren] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAssign, setShowAssign] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchChildren(parent.id)
      .then((list) => !cancelled && setChildren(list))
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Не удалось загрузить детей');
      });
    return () => {
      cancelled = true;
    };
  }, [parent.id, version]);

  const linkedIds = new Set((children ?? []).map((c) => c.id));
  const candidates = allUsers.filter((u) => u.role === 'student' && !linkedIds.has(u.id));

  return (
    <div className="children-section">
      <div className="children-section__head">
        <span>Дети</span>
        <Button variant="secondary" onClick={() => setShowAssign(true)}>
          Привязать детей
        </Button>
      </div>

      {error && <div className="form-error">{error}</div>}

      {children === null ? (
        <div className="admin-empty">Загрузка…</div>
      ) : children.length === 0 ? (
        <div className="admin-empty">Дети пока не привязаны</div>
      ) : (
        <div className="profile-rows">
          {children.map((c) => (
            <div key={c.id} className="profile-row">
              <span>{c.full_name}</span>
              <span>{c.email}</span>
            </div>
          ))}
        </div>
      )}

      {showAssign && (
        <AssignChildrenModal
          parent={parent}
          candidates={candidates}
          onClose={() => setShowAssign(false)}
          onAssigned={() => {
            setShowAssign(false);
            setVersion((v) => v + 1);
          }}
        />
      )}
    </div>
  );
}

function AssignChildrenModal({
  parent,
  candidates,
  onClose,
  onAssigned,
}: {
  parent: User;
  candidates: User[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
      await assignChildren(parent.id, [...checked]);
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось привязать детей');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Дети — ${parent.full_name}`} onClose={onClose}>
      {candidates.length === 0 ? (
        <div className="admin-empty">Все ученики уже привязаны к этому родителю</div>
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
          {submitting ? 'Сохраняем…' : `Привязать (${checked.size})`}
        </Button>
      </div>
    </Modal>
  );
}
