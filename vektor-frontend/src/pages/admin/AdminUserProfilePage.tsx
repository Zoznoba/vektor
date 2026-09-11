import { useEffect, useMemo, useState } from "react";
import {
  Navigate,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { AdminShell } from "./AdminShell";
import { Panel } from "../../components/ui/Panel";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Avatar } from "../../components/ui/Avatar";
import { Modal } from "../../components/ui/Modal";
import { Collapsible } from "../../components/ui/Collapsible";
import { Icon } from "../../components/icons/Icon";
import { StudentResultsPanel } from "../../components/dashboard/StudentResultsPanel";
import { useApi } from "../../hooks/useApi";
import {
  fetchUsers,
  fetchChildren,
  assignChildren,
  setUserActive,
} from "../../api/users";
import { fetchClasses } from "../../api/classes";
import { fetchCases } from "../../api/cases";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { ROLE_BADGE, ROLE_LABELS } from "../../types/auth";
import { withPlural } from "../../data/plural";
import type { User } from "../../types/auth";
import { classLabel } from "../../types/school";
import type { SchoolClass } from "../../types/school";
import {
  DeactivateModal,
  EditUserModal,
  ResetPasswordModal,
} from "./AdminUsersPage";
import "./admin.css";

/** Сколько классов показываем чипами до «+ ещё N». */
const CLASS_CHIP_LIMIT = 4;

/**
 * Карточка одного пользователя глазами админа.
 *
 * Заменяет раскрывающуюся панель «Действия» на «Пользователях»: та вставлялась
 * НАД таблицей и сдвигала её вниз, а сюда помещается всё, чему в списке было
 * тесно.
 *
 * Всё живёт на ОДНОЙ странице, без вкладок: у человека ровно один набор
 * связей, и отдельная вкладка «Обзор» повторяла бы строками (email, роль,
 * статус) то, что и так написано в шапке. Класс и кейс — чипами прямо в
 * шапке, а диагностика — сворачиваемый блок внизу, тем же приёмом, что
 * аналитика класса в «Классах» и кейса в «Кейсах».
 *
 * Своего пункта в сайдбаре нет намеренно: это ветка «Пользователей» (отсюда и
 * URL, и подсветка `users`). Адрес у карточки ровно один: синоним
 * `/admin/users/:id/results` давал ту же самую страницу и удалён.
 *
 * Самого пользователя берём из общего списка, а не отдельным запросом: ручки
 * `GET /users/{id}` у бэкенда нет, а классы и кейсы этому экрану нужны в любом
 * случае — ради связей в шапке.
 */
export function AdminUserProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { user: currentUser } = useAuth();

  const users = useApi(fetchUsers);
  const classes = useApi(fetchClasses);
  const cases = useApi(fetchCases);

  // Раскрыт сразу: ради диагностики карточку ученика и открывают чаще
  // всего, а лишний клик по каждому ученику — это лишний клик по каждому
  // ученику. Свернуть вручную можно, состояние переживает только эту
  // страницу.
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(true);
  // Предметник ведёт до десятка классов, и ряд чипов вытеснял бы из шапки
  // всё остальное. Раскрытие одностороннее: свернуть обратно нечего —
  // список коротких пилюль, а не панель.
  const [allClassesShown, setAllClassesShown] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [resetPasswordOpen, setResetPasswordOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const subjectId = Number(id);
  const user = useMemo(
    () => (users.data ?? []).find((u) => u.id === subjectId) ?? null,
    [users.data, subjectId],
  );

  const userClasses = useMemo(() => {
    if (!user) return [];
    const all = classes.data ?? [];
    return user.role === "student"
      ? all.filter((c) => c.students.some((s) => s.id === user.id))
      : all.filter((c) => c.teachers.some((t) => t.teacher.id === user.id));
  }, [classes.data, user]);

  // Кейс один на человека — ищем по составу, а не по user.case_id: в кейсе
  // ученик и учитель лежат в разных списках, но членство одно.
  const userCase = useMemo(() => {
    if (!user) return null;
    return (
      (cases.data ?? []).find((c) =>
        [...c.students, ...c.teachers].some((m) => m.id === user.id),
      ) ?? null
    );
  }, [cases.data, user]);

  const visibleClasses = allClassesShown
    ? userClasses
    : userClasses.slice(0, CLASS_CHIP_LIMIT);
  const hiddenClassCount = userClasses.length - visibleClasses.length;

  if (!Number.isFinite(subjectId))
    return <Navigate to="/admin/users" replace />;

  // Экран открывают из списка и из трёх других разделов, поэтому «назад» — это
  // история, а не фиксированный адрес. По прямой ссылке истории нет
  // (`key === 'default'`) — уводим в «Пользователей» с подсвеченной строкой.
  const goBack = () =>
    location.key === "default"
      ? navigate("/admin/users", { state: { userId: subjectId } })
      : navigate(-1);

  const handleActivate = async () => {
    if (!user) return;
    setError(null);
    setSubmitting(true);
    try {
      await setUserActive(user.id, true);
      users.reload();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Не удалось активировать пользователя",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AdminShell activeNavKey="users">
      <div className="admin-toolbar">
        <h2>{user?.full_name ?? "Пользователь"}</h2>
        <div className="admin-toolbar__spacer" />
        <Button variant="secondary" onClick={goBack}>
          ← Назад
        </Button>
      </div>

      {users.error && <div className="form-error">{users.error}</div>}
      {error && <div className="form-error">{error}</div>}

      {users.loading && !users.data ? (
        <Panel>
          <div className="admin-empty">Загрузка…</div>
        </Panel>
      ) : !user ? (
        <Panel>
          <div className="admin-empty">
            Пользователь не найден — возможно, его уже удалили
          </div>
        </Panel>
      ) : (
        <>
          <Panel>
            <div className="user-card">
              <Avatar fullName={user.full_name} className="user-card__avatar" />
              <div className="user-card__main">
                <div className="user-card__name">{user.full_name}</div>
                <div className="user-card__meta">
                  <Badge variant={ROLE_BADGE[user.role]}>
                    {ROLE_LABELS[user.role]}
                  </Badge>
                  <span>{user.email}</span>
                  <span>
                    <span
                      className={`status-dot ${user.is_active ? "status-dot--on" : ""}`.trim()}
                    />
                    {user.is_active ? "Активен" : "Неактивен"}
                  </span>
                  {/* Дата рождения есть только у тех, кого завели из списков
                      состава: у остальных строки нет вовсе, а не «не указана»
                      — пустое поле читалось бы как недозагрузка. */}
                  {user.birth_date && (
                    <span>{birthDateLabel(user.birth_date)}</span>
                  )}
                </div>

                {/* Связи — здесь же, а не отдельным блоком: это чипы того же
                    рода, что фильтры и бейджи ролей, а не список. Голыми
                    синими ссылками («7-2 →») они были единственным таким
                    элементом на весь проект и выпадали из стиля. Роль, у
                    которой связей не бывает (админ), строку не получает
                    вовсе: «не состоит нигде» пустым блоком читалось бы как
                    незагрузившийся экран. */}
                {(userClasses.length > 0 || userCase !== null) && (
                  <div className="user-card__links">
                    {visibleClasses.map((cls) => (
                      <button
                        key={cls.id}
                        type="button"
                        className="entity-chip"
                        title={`Открыть класс ${classLabel(cls)}`}
                        onClick={() =>
                          navigate("/admin/classes", {
                            state: { classId: cls.id },
                          })
                        }
                      >
                        <Icon name="school" size={14} />
                        {classLabel(cls)}
                        {teacherRoleSuffix(cls, user) && (
                          <span className="entity-chip__note">
                            {teacherRoleSuffix(cls, user)}
                          </span>
                        )}
                      </button>
                    ))}
                    {hiddenClassCount > 0 && (
                      <button
                        type="button"
                        className="entity-chip entity-chip--more"
                        onClick={() => setAllClassesShown(true)}
                      >
                        + ещё {hiddenClassCount}
                      </button>
                    )}
                    {userCase && (
                      <button
                        type="button"
                        className="entity-chip"
                        title={`Открыть кейс «${userCase.name}»`}
                        onClick={() =>
                          navigate("/admin/cases", {
                            state: { caseId: userCase.id },
                          })
                        }
                      >
                        <Icon name="briefcase" size={14} />
                        {userCase.name}
                      </button>
                    )}
                  </div>
                )}
              </div>

              <div className="user-card__actions">
                <Button variant="secondary" onClick={() => setEditOpen(true)}>
                  Редактировать
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setResetPasswordOpen(true)}
                >
                  Сбросить пароль
                </Button>
                {user.is_active ? (
                  <Button
                    variant="danger"
                    onClick={() => setDeactivateOpen(true)}
                    disabled={user.id === currentUser?.id}
                    title={
                      user.id === currentUser?.id
                        ? "Нельзя деактивировать собственную учётную запись"
                        : undefined
                    }
                  >
                    Деактивировать
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    onClick={handleActivate}
                    disabled={submitting}
                  >
                    {submitting ? "Активируем…" : "Активировать"}
                  </Button>
                )}
              </div>
            </div>
          </Panel>

          {/* Дети — единственная связь, которой нужен свой блок: это список
              людей, а не одна ссылка, и приходит он отдельным запросом. */}
          {user.role === "parent" && <ChildrenPanel parent={user} />}

          {/* Диагностика — сворачиваемый блок, как аналитика класса и кейса,
              но раскрытый по умолчанию: в отличие от школьных агрегатов это
              главное, за чем открывают карточку ученика. */}
          {user.role === "student" && (
            <Collapsible
              title="Диагностика"
              hint="Профиль по критериям, зоны роста и динамика по годам"
              open={diagnosticsOpen}
              onToggle={() => setDiagnosticsOpen((value) => !value)}
            >
              <StudentResultsPanel
                subjectId={user.id}
                title="Результаты"
                subjectShownOutside
              />
            </Collapsible>
          )}
        </>
      )}

      {user && editOpen && (
        <EditUserModal
          user={user}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            setEditOpen(false);
            users.reload();
          }}
        />
      )}

      {user && resetPasswordOpen && (
        <ResetPasswordModal
          user={user}
          onClose={() => setResetPasswordOpen(false)}
        />
      )}

      {user && deactivateOpen && (
        <DeactivateModal
          users={[user]}
          onClose={() => setDeactivateOpen(false)}
          onDone={() => {
            setDeactivateOpen(false);
            users.reload();
          }}
        />
      )}
    </AdminShell>
  );
}

/** «17 апреля 2011 · 15 лет» — дата рождения вместе с возрастом.
 *
 * Возраст здесь и есть смысл строки: админ смотрит на неё, чтобы понять,
 * тому ли классу человек соответствует, а «2011-04-17» этого не говорит.
 * Месяц берём у Intl: в составе даты нужен родительный падеж («17 апреля»),
 * ровно тот, что даёт toLocaleDateString — в отличие от списка месяцев в
 * data/period.ts, где нужен именительный («Июнь 2026»).
 */
function birthDateLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  const formatted = date.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return `${formatted} · ${withPlural(ageYears(date), ["год", "года", "лет"])}`;
}

/** Полных лет на сегодня. */
function ageYears(birth: Date): number {
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const hadBirthday =
    today.getMonth() > birth.getMonth() ||
    (today.getMonth() === birth.getMonth() &&
      today.getDate() >= birth.getDate());
  if (!hadBirthday) age -= 1;
  return age;
}

/** «кл. рук» / «физика» — приписка на чипе класса, только для учителя. У
 *  ученика класс один и без уточнений: он в нём просто учится. */
function teacherRoleSuffix(cls: SchoolClass, user: User): string {
  if (user.role !== "teacher") return "";
  const link = cls.teachers.find((t) => t.teacher.id === user.id);
  if (!link) return "";
  if (link.is_homeroom) return "кл. рук";
  return link.subject ?? "";
}

/** Дети родителя. Единственный блок, которому нужен свой запрос: связь
 *  «родитель → дети» не приходит ни со списком пользователей, ни с классами. */
function ChildrenPanel({ parent }: { parent: User }) {
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
        setError(
          err instanceof ApiError ? err.message : "Не удалось загрузить детей",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [parent.id, version]);

  return (
    <Panel title="Дети">
      <div className="children-section__head">
        <span>Привязанные ученики</span>
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
          linkedIds={new Set((children ?? []).map((c) => c.id))}
          onClose={() => setShowAssign(false)}
          onAssigned={() => {
            setShowAssign(false);
            setVersion((v) => v + 1);
          }}
        />
      )}
    </Panel>
  );
}

/**
 * Привязка детей к родителю. Кандидатов ищем поиском, а не одним длинным
 * списком: учеников в школе больше сотни, а детей у родителя один-два.
 */
function AssignChildrenModal({
  parent,
  linkedIds,
  onClose,
  onAssigned,
}: {
  parent: User;
  linkedIds: Set<number>;
  onClose: () => void;
  onAssigned: () => void;
}) {
  const users = useApi(fetchUsers);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const candidates = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (users.data ?? []).filter(
      (u) =>
        u.role === "student" &&
        !linkedIds.has(u.id) &&
        (!query ||
          u.full_name.toLowerCase().includes(query) ||
          u.email.toLowerCase().includes(query)),
    );
  }, [users.data, linkedIds, search]);

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
      setError(
        err instanceof ApiError ? err.message : "Не удалось привязать детей",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title={`Дети — ${parent.full_name}`} onClose={onClose}>
      <div className="search-box search-box--block">
        <Icon name="search" size={16} />
        <input
          type="search"
          placeholder="Поиск ученика"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {users.loading && !users.data ? (
        <div className="admin-empty">Загрузка…</div>
      ) : candidates.length === 0 ? (
        <div className="admin-empty">Подходящих учеников не нашлось</div>
      ) : (
        <div className="assign-list">
          {candidates.map((u) => (
            <label key={u.id} className="assign-item">
              <input
                type="checkbox"
                checked={checked.has(u.id)}
                onChange={() => toggle(u.id)}
              />
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
        <Button
          onClick={handleSubmit}
          disabled={submitting || checked.size === 0}
        >
          {submitting ? "Сохраняем…" : `Привязать (${checked.size})`}
        </Button>
      </div>
    </Modal>
  );
}
