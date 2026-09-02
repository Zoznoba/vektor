import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Icon } from '../../components/icons/Icon';
import { ActionMenu } from '../../components/ui/ActionMenu';
import type { ActionMenuItem } from '../../components/ui/ActionMenu';
import { SelectAllCheckbox, SelectionBar } from '../../components/ui/SelectionBar';
import { useApi } from '../../hooks/useApi';
import { useRowSelection } from '../../hooks/useRowSelection';
import type { RowSelection } from '../../hooks/useRowSelection';
import {
  fetchCases,
  createCase,
  updateCase,
  assignCaseStudents,
  assignCaseTeachers,
  removeCaseMembers,
  deleteCase,
} from '../../api/cases';
import { fetchUsers } from '../../api/users';
import { ApiError } from '../../api/client';
import { caseMembers } from '../../types/case';
import type { Case } from '../../types/case';
import type { User } from '../../types/auth';
import './admin.css';

/** Вкладки состава. Определяют и таблицу, и контекстную кнопку добавления. */
type MemberTab = 'students' | 'teachers';

const TABS: { key: MemberTab; label: string }[] = [
  { key: 'students', label: 'Ученики' },
  { key: 'teachers', label: 'Учителя' },
];

/**
 * Практика школы — 2–3 учителя на кейс. Это НЕ инвариант данных, бэкенд
 * границы не знает (см. CLAUDE.md, Этап 8), поэтому здесь только подсказка,
 * которая ничего не блокирует — как предупреждение про 2–4 учителей в панели
 * генерации анкет.
 */
const USUAL_TEACHERS_MAX = 3;

/** Стабильная пустая ссылка: иначе `[]` в рендере ломает мемоизацию выбора. */
const EMPTY_ROWS: User[] = [];

/**
 * «Кейсы» — админский экран профильных групп (кружков). Устроен как
 * AdminClassesPage: сетка карточек сверху, состав выбранного по вкладкам
 * снизу, действия по строке — в дропдауне.
 *
 * Отличие от класса, которое видно в UI: членство в кейсе ОДНО и у ученика,
 * и у учителя, поэтому кандидатом на привязку может быть только человек, не
 * состоящий ни в каком кейсе (бэкенд на чужого участника отвечает 409 —
 * перевод делается явно, через открепление).
 */
export function AdminCasesPage() {
  const cases = useApi(fetchCases);
  const users = useApi(fetchUsers);

  const location = useLocation();
  // Переход «Кейс …» из карточки пользователя (AdminUsersPage) кладёт id в
  // state — тем же приёмом, что и переход в класс: открывается нужный кейс,
  // а не первый по алфавиту.
  const [selectedId, setSelectedId] = useState<number | null>(
    () => (location.state as { caseId?: number } | null)?.caseId ?? null,
  );
  const [tab, setTab] = useState<MemberTab>('students');
  const [showCreate, setShowCreate] = useState(false);
  // Режим модалки назначения совпадает с активной вкладкой: «добавить»
  // всегда добавляет именно тех, кого показывает вкладка.
  const [assignMode, setAssignMode] = useState<MemberTab | null>(null);
  const [renaming, setRenaming] = useState<Case | null>(null);
  const [detaching, setDetaching] = useState<{ users: User[]; kase: Case } | null>(null);
  const [deleting, setDeleting] = useState<Case | null>(null);

  // Порядок по названию — тот же, что отдаёт бэкенд; держим его и на клиенте,
  // чтобы карточки не прыгали после reload.
  const sorted = useMemo(
    () => [...(cases.data ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'ru')),
    [cases.data],
  );

  // Выбранный кейс всегда берём из свежих данных (после reload объект новый);
  // пока ничего не выбрано — показываем первый, чтобы состав не был пустым.
  const selected = sorted.find((c) => c.id === selectedId) ?? sorted[0] ?? null;

  const rows = selected ? selected[tab] : EMPTY_ROWS;
  // Идентичность массива важна: она уходит в useMemo/useCallback внутри
  // useRowSelection, а `selected[tab]` стабилен между рендерами.
  const rowIds = useMemo(() => rows.map((u) => u.id), [rows]);
  // resetKey — кейс + вкладка: выбор не должен переживать ни переключение
  // вкладки, ни переход на другой кейс (иначе откреплялись бы невидимые люди).
  const selection = useRowSelection(rowIds, `${selected?.id ?? 'none'}:${tab}`);

  const addLabel: Record<MemberTab, string> = {
    students: 'Добавить учеников',
    teachers: 'Добавить учителей',
  };

  return (
    <AdminShell activeNavKey="cases">
      <div className="admin-toolbar">
        <h2>Кейсы</h2>
        <div className="admin-toolbar__spacer" />
        <Button onClick={() => setShowCreate(true)}>
          <Icon name="plus" size={15} />
          Создать кейс
        </Button>
      </div>

      {cases.error && <div className="form-error">{cases.error}</div>}

      {/* Спиннер только на ПЕРВОЙ загрузке: reload после мутации оставляет
          данные на экране, а подмена всего блока размонтировала бы панель
          вместе с её состоянием. */}
      {cases.loading && !cases.data ? (
        <Panel>
          <div className="admin-empty">Загрузка…</div>
        </Panel>
      ) : sorted.length === 0 ? (
        <Panel>
          <div className="admin-empty">
            Кейсов пока нет — создайте первый кнопкой «Создать кейс»
          </div>
        </Panel>
      ) : (
        <>
          <div className="class-grid">
            {sorted.map((kase) => (
              <button
                key={kase.id}
                className={`class-card ${kase.id === selected?.id ? 'class-card--selected' : ''}`.trim()}
                onClick={() => setSelectedId(kase.id)}
                title={kase.name}
              >
                <div className="class-card__name">{kase.name}</div>
                <div className="class-card__count">{studentsCountLabel(kase.students.length)}</div>
                <div className="class-card__teachers">
                  {teachersCountLabel(kase.teachers.length)}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <Panel title={`Состав кейса «${selected.name}»`}>
              {selected.description && (
                <p className="roster-hint">{selected.description}</p>
              )}

              <div className="class-tabs">
                <div className="filter-chips">
                  {TABS.map((t) => (
                    <button
                      key={t.key}
                      className={`filter-chip ${tab === t.key ? 'filter-chip--active' : ''}`.trim()}
                      onClick={() => setTab(t.key)}
                    >
                      {t.label} · {selected[t.key].length}
                    </button>
                  ))}
                </div>
                <div className="admin-toolbar__spacer" />
                <ActionMenu
                  trigger={<Icon name="settings" size={15} />}
                  items={[
                    {
                      key: 'rename',
                      label: 'Переименовать кейс',
                      onSelect: () => setRenaming(selected),
                    },
                    {
                      key: 'delete',
                      label: 'Удалить кейс',
                      danger: true,
                      onSelect: () => setDeleting(selected),
                    },
                  ]}
                />
                <Button variant="secondary" onClick={() => setAssignMode(tab)}>
                  <Icon name="plus" size={15} />
                  {addLabel[tab]}
                </Button>
              </div>

              <SelectionBar
                selection={selection}
                itemLabel={tab === 'students' ? studentsCountLabel : teachersCountLabel}
              >
                <Button
                  variant="danger"
                  onClick={() =>
                    setDetaching({
                      users: rows.filter((u) => selection.selectedIds.includes(u.id)),
                      kase: selected,
                    })
                  }
                >
                  Открепить от кейса
                </Button>
              </SelectionBar>

              <MembersTable
                kase={selected}
                tab={tab}
                selection={selection}
                onDetach={(user) => setDetaching({ users: [user], kase: selected })}
              />
            </Panel>
          )}
        </>
      )}

      {showCreate && (
        <CaseFormModal
          title="Новый кейс"
          submitLabel="Создать"
          onClose={() => setShowCreate(false)}
          onSubmit={async (name, description) => {
            const created = await createCase(name, description);
            setSelectedId(created.id);
            setShowCreate(false);
            cases.reload();
          }}
        />
      )}

      {renaming && (
        <CaseFormModal
          title={`Кейс «${renaming.name}»`}
          submitLabel="Сохранить"
          initialName={renaming.name}
          initialDescription={renaming.description ?? ''}
          onClose={() => setRenaming(null)}
          onSubmit={async (name, description) => {
            await updateCase(renaming.id, { name, description });
            setRenaming(null);
            cases.reload();
          }}
        />
      )}

      {assignMode && selected && (
        <AssignMembersModal
          mode={assignMode}
          kase={selected}
          allCases={sorted}
          allUsers={users.data ?? []}
          onClose={() => setAssignMode(null)}
          onAssigned={() => {
            setAssignMode(null);
            cases.reload();
          }}
        />
      )}

      {detaching && (
        <DetachMembersModal
          users={detaching.users}
          kase={detaching.kase}
          onClose={() => setDetaching(null)}
          onDetached={() => {
            setDetaching(null);
            selection.clear();
            cases.reload();
          }}
        />
      )}

      {deleting && (
        <DeleteCaseModal
          kase={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            // Выбор сбрасываем: удалённый кейс больше не придёт в списке, а
            // selectedId на него бы остался.
            setSelectedId(null);
            cases.reload();
          }}
        />
      )}
    </AdminShell>
  );
}

function MembersTable({
  kase,
  tab,
  selection,
  onDetach,
}: {
  kase: Case;
  tab: MemberTab;
  selection: RowSelection;
  onDetach: (user: User) => void;
}) {
  const navigate = useNavigate();
  const rows = kase[tab];

  if (rows.length === 0) {
    return (
      <div className="admin-empty">
        {tab === 'students'
          ? 'В кейсе пока нет учеников'
          : 'К кейсу пока не привязан ни один учитель'}
      </div>
    );
  }

  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th className="admin-table__select-col">
            <SelectAllCheckbox selection={selection} />
          </th>
          <th>{tab === 'students' ? 'Ученик' : 'Учитель'}</th>
          <th>Email</th>
          <th>Статус</th>
          <th className="admin-table__actions-col" />
        </tr>
      </thead>
      <tbody>
        {rows.map((member) => (
          <tr key={member.id}>
            <td className="admin-table__select-col">
              <input
                type="checkbox"
                aria-label={`Выбрать: ${member.full_name}`}
                checked={selection.has(member.id)}
                onChange={() => selection.toggle(member.id)}
              />
            </td>
            <td>{member.full_name}</td>
            <td>{member.email}</td>
            <td>
              <span className={`status-dot ${member.is_active ? 'status-dot--on' : ''}`.trim()} />
              {member.is_active ? 'Активен' : 'Неактивен'}
            </td>
            <td className="admin-table__actions-col">
              <ActionMenu
                trigger={<Icon name="chevronDown" size={15} />}
                items={[
                  ...commonUserActions(member, navigate),
                  {
                    key: 'detach',
                    label: 'Открепить от кейса',
                    danger: true,
                    onSelect: () => onDetach(member),
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

/** Пункты «профиль» и «результаты» — те же, что в составе класса. */
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

/** Одна форма на создание и переименование — поля те же, разнится только текст. */
function CaseFormModal({
  title,
  submitLabel,
  initialName = '',
  initialDescription = '',
  onClose,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  initialName?: string;
  initialDescription?: string;
  onClose: () => void;
  onSubmit: (name: string, description: string | null) => Promise<void>;
}) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Пустое описание — это «стереть», отправляем null: бэкенд различает
      // отсутствие ключа и явный null.
      await onSubmit(name.trim(), description.trim() || null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить кейс');
      setSubmitting(false);
    }
  };

  return (
    <Modal title={title} onClose={onClose}>
      <label className="form-field">
        <span>Название</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Робототехника"
          maxLength={255}
          autoFocus
        />
      </label>
      <label className="form-field">
        <span>Описание (необязательно)</span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Кружок для 5–8 классов, вторник и четверг"
          maxLength={500}
        />
      </label>

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting || name.trim().length === 0}>
          {submitting ? 'Сохраняем…' : submitLabel}
        </Button>
      </div>
    </Modal>
  );
}

function AssignMembersModal({
  mode,
  kase,
  allCases,
  allUsers,
  onClose,
  onAssigned,
}: {
  mode: MemberTab;
  kase: Case;
  allCases: Case[];
  allUsers: User[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const candidates = useMemo(() => {
    // Кейс у человека ровно ОДИН, поэтому уже занятые не предлагаются вовсе:
    // бэкенд ответил бы 409 на всю пачку. Перевод — через открепление, и это
    // сознательно ручной путь (иначе привязка молча выкинула бы человека из
    // прежнего кейса).
    const busy = new Set(allCases.flatMap((c) => caseMembers(c).map((u) => u.id)));
    // Неактивные не предлагаются: под этим флагом ходят и деактивированные
    // админом люди, и служебные респонденты архивного импорта.
    const role = mode === 'students' ? 'student' : 'teacher';
    return allUsers.filter((u) => u.is_active && u.role === role && !busy.has(u.id));
  }, [mode, allCases, allUsers]);

  // Поиск фильтрует ТОЛЬКО показ: отмеченные галочки живут в `checked` и не
  // сбрасываются, когда человек уходит из выдачи, — иначе набрать выборку по
  // нескольким запросам было бы невозможно. Список уже загружен целиком
  // (`fetchUsers`), поэтому фильтруем на клиенте, без debounce и запроса.
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return candidates;
    // Слова запроса — в любом порядке: «алина астахова» находит
    // «Астахова Алина» так же, как «астахова алина».
    const words = q.split(/\s+/);
    return candidates.filter((u) => {
      const name = u.full_name.toLowerCase();
      return words.every((w) => name.includes(w));
    });
  }, [candidates, search]);

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
      if (mode === 'students') await assignCaseStudents(kase.id, ids);
      else await assignCaseTeachers(kase.id, ids);
      onAssigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить назначение');
    } finally {
      setSubmitting(false);
    }
  };

  const teachersAfter = kase.teachers.length + checked.size;
  const tooManyTeachers = mode === 'teachers' && teachersAfter > USUAL_TEACHERS_MAX;

  return (
    <Modal
      title={
        mode === 'students' ? `Ученики в «${kase.name}»` : `Учителя кейса «${kase.name}»`
      }
      onClose={onClose}
    >
      {candidates.length === 0 ? (
        <div className="admin-empty">
          {mode === 'students'
            ? 'Свободных учеников нет — все уже состоят в кейсах'
            : 'Свободных учителей нет — все уже ведут кейсы'}
        </div>
      ) : (
        <>
          <p className="roster-hint">
            {mode === 'students'
              ? 'Кейс собирается через параллели — ученики разных классов здесь в порядке вещей.'
              : `Обычно кейс ведут 2–${USUAL_TEACHERS_MAX} учителя.`}{' '}
            В списке только те, кто не состоит ни в одном кейсе: чтобы перевести человека,
            сначала открепите его от прежнего.
          </p>
          <div className="search-box search-box--block">
            <Icon name="search" size={16} />
            <input
              type="search"
              placeholder="Поиск по имени и фамилии"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="assign-list">
            {visible.length === 0 ? (
              <div className="admin-empty">Никого не нашлось</div>
            ) : (
              visible.map((u) => (
                <label key={u.id} className="assign-item">
                  <input
                    type="checkbox"
                    checked={checked.has(u.id)}
                    onChange={() => toggle(u.id)}
                  />
                  <span className="assign-item__name">{u.full_name}</span>
                  <span className="assign-item__email">{u.email}</span>
                </label>
              ))
            )}
          </div>
        </>
      )}

      {/* Предупреждение, а не запрет: 2–3 — практика школы, а не правило данных. */}
      {tooManyTeachers && (
        <p className="roster-hint">
          Получится {teachersAfter} учителей — обычно берут 2–{USUAL_TEACHERS_MAX}. Сохранить
          всё равно можно.
        </p>
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

function DetachMembersModal({
  users,
  kase,
  onClose,
  onDetached,
}: {
  users: User[];
  kase: Case;
  onClose: () => void;
  onDetached: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Один вызов и на одного человека, и на пачку: бэкенд-ручка bulk и
      // атомарна, отдельный путь для одиночного случая только разъехался бы.
      await removeCaseMembers(
        kase.id,
        users.map((u) => u.id),
      );
      onDetached();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось открепить');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Открепить от кейса" onClose={onClose}>
      <p className="roster-hint">
        {users.length === 1
          ? `${users[0].full_name} будет откреплён от кейса «${kase.name}».`
          : `${memberCountLabel(users.length)} будут откреплены от кейса «${kase.name}».`}{' '}
        Люди останутся в системе со всей историей — после этого их можно привязать к другому
        кейсу.
      </p>

      {/* Поимённо, а не одним счётчиком: выделение собиралось галочками, и
          последняя возможность заметить лишнего — здесь. */}
      {users.length > 1 && (
        <ul className="detach-list">
          {users.map((u) => (
            <li key={u.id}>{u.full_name}</li>
          ))}
        </ul>
      )}

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button variant="danger" onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'Открепляем…' : 'Открепить'}
        </Button>
      </div>
    </Modal>
  );
}

function DeleteCaseModal({
  kase,
  onClose,
  onDeleted,
}: {
  kase: Case;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const memberCount = caseMembers(kase).length;

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await deleteCase(kase.id);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось удалить кейс');
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Удалить кейс" onClose={onClose}>
      {memberCount > 0 ? (
        // Состояние проверяем и здесь, до запроса: бэкенд всё равно ответит
        // 409, но объяснить, ЧТО делать, лучше до нажатия.
        <p className="roster-hint">
          В кейсе «{kase.name}» ещё {memberCount} {memberLabel(memberCount)}. Удалить можно
          только пустой кейс — сначала открепите всех на вкладках состава.
        </p>
      ) : (
        <p className="roster-hint">
          Кейс «{kase.name}» будет удалён. Он пуст, поэтому ничьи данные не пострадают.
        </p>
      )}

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          {memberCount > 0 ? 'Понятно' : 'Отмена'}
        </Button>
        {memberCount === 0 && (
          <Button variant="danger" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Удаляем…' : 'Удалить кейс'}
          </Button>
        )}
      </div>
    </Modal>
  );
}

function memberCountLabel(n: number): string {
  return `${n} ${memberLabel(n)}`;
}

function memberLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'участник';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'участника';
  return 'участников';
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
