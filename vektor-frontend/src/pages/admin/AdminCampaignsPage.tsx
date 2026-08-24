import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { Icon } from '../../components/icons/Icon';
import { useApi } from '../../hooks/useApi';
import {
  fetchCampaigns,
  createCampaign,
  generateAssessments,
  closeCampaign,
  reopenCampaign,
  fetchCampaignCoverage,
} from '../../api/campaigns';
import type { CreateCampaignIn } from '../../api/campaigns';
import { fetchClasses } from '../../api/classes';
import { classLabel } from '../../types/school';
import { MONTH_OPTIONS, formatPeriod } from '../../data/period';
import type { SchoolClass } from '../../types/school';
import { ApiError } from '../../api/client';
import type { CampaignCoverage, CampaignListItem, CampaignStatus } from '../../types/campaign';
import './admin.css';
import './campaigns.css';

const STATUS_LABEL: Record<CampaignStatus, string> = {
  draft: 'Черновик',
  active: 'Активна',
  closed: 'Завершена',
};

const STATUS_BADGE: Record<CampaignStatus, 'gray' | 'lime' | 'blue'> = {
  draft: 'gray',
  active: 'lime',
  closed: 'blue',
};

const STATUS_FILTERS: { key: CampaignStatus; label: string }[] = [
  { key: 'active', label: 'Активные' },
  { key: 'draft', label: 'Черновики' },
  { key: 'closed', label: 'Завершённые' },
];

/**
 * «Диагностика» — админский экран из прототипа (isAdminCampaign, там
 * назывался «Кампании 360°»): список кампаний, покрытие по классам,
 * генерация анкет. Карточка импорта Google Sheets из прототипа сюда
 * сознательно не попала — Этап 6 не начат, демо закрыто SQL-дампом
 * (см. CLAUDE.md). Внутри домен всё ещё называется campaign — переименован
 * только пользовательский текст (пункт меню, заголовок), не сущность.
 */
export function AdminCampaignsPage() {
  const navigate = useNavigate();
  const campaigns = useApi(fetchCampaigns);
  const classes = useApi(fetchClasses);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  // По умолчанию — только активные: это то, за чем админ обычно следит.
  const [statusFilter, setStatusFilter] = useState<Set<CampaignStatus>>(
    () => new Set<CampaignStatus>(['active']),
  );

  const toggleStatusFilter = (key: CampaignStatus) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const sorted = useMemo(
    () => [...(campaigns.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [campaigns.data],
  );
  const countByStatus = useMemo(() => {
    const counts: Record<CampaignStatus, number> = { draft: 0, active: 0, closed: 0 };
    for (const c of sorted) counts[c.status] += 1;
    return counts;
  }, [sorted]);
  const filtered = useMemo(
    () => sorted.filter((c) => statusFilter.has(c.status)),
    [sorted, statusFilter],
  );
  const selected = filtered.find((c) => c.id === selectedId) ?? filtered[0] ?? null;

  return (
    <AdminShell activeNavKey="tests">
      <div className="admin-toolbar">
        <h2>Диагностика</h2>
        <div className="filter-chips">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              className={`filter-chip ${statusFilter.has(f.key) ? 'filter-chip--active' : ''}`.trim()}
              onClick={() => toggleStatusFilter(f.key)}
            >
              {f.label} · {countByStatus[f.key]}
            </button>
          ))}
        </div>
        <div className="admin-toolbar__spacer" />
        <Button variant="secondary" onClick={() => navigate('/admin/questionnaire')}>
          <Icon name="file" size={15} />
          Конструктор анкеты
        </Button>
        <Button onClick={() => setShowCreate(true)}>
          <Icon name="plus" size={15} />
          Новая кампания
        </Button>
      </div>

      {campaigns.error && <div className="form-error">{campaigns.error}</div>}

      {/* Спиннер только на ПЕРВОЙ загрузке: reload после мутации оставляет
          данные на экране, а подмена всего блока размонтировала бы панель
          вместе с её состоянием — сообщение о результате исчезало. */}
      {campaigns.loading && !campaigns.data ? (
        <Panel>
          <div className="admin-empty">Загрузка…</div>
        </Panel>
      ) : sorted.length === 0 ? (
        <Panel>
          <div className="admin-empty">
            Кампаний пока нет — создайте первую кнопкой «Новая кампания»
          </div>
        </Panel>
      ) : filtered.length === 0 ? (
        <Panel>
          <div className="admin-empty">Отметьте хотя бы один статус, чтобы увидеть кампании</div>
        </Panel>
      ) : (
        <>
          <div className="campaign-grid">
            {filtered.map((c) => (
              <button
                key={c.id}
                className={`campaign-card ${
                  c.id === selected?.id ? 'campaign-card--selected' : ''
                }`.trim()}
                onClick={() => setSelectedId(c.id)}
              >
                <div className="campaign-card__head">
                  <Badge variant={STATUS_BADGE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
                  <span className="campaign-card__period">
                    {formatPeriod(c.period_year, c.period_month)}
                  </span>
                </div>
                <div className="campaign-card__title">{c.title}</div>
                <ProgressBar
                  value={
                    c.total_assessments > 0
                      ? (c.completed_assessments / c.total_assessments) * 100
                      : 0
                  }
                  className="campaign-card__bar"
                />
                <div className="campaign-card__progress">
                  {c.completed_assessments} из {c.total_assessments} анкет
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <div className="campaign-detail">
              <CoveragePanel
                key={`coverage-${selected.id}`}
                campaign={selected}
                onChanged={() => campaigns.reload()}
              />
              <GeneratePanel
                key={`generate-${selected.id}`}
                campaign={selected}
                allClasses={classes.data ?? []}
                onGenerated={() => campaigns.reload()}
              />
            </div>
          )}
        </>
      )}

      {showCreate && (
        <CreateCampaignModal
          onClose={() => setShowCreate(false)}
          onCreated={(id) => {
            setShowCreate(false);
            setSelectedId(id);
            campaigns.reload();
          }}
        />
      )}
    </AdminShell>
  );
}

function CoveragePanel({
  campaign,
  onChanged,
}: {
  campaign: CampaignListItem;
  onChanged: () => void;
}) {
  const [coverage, setCoverage] = useState<CampaignCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [reopening, setReopening] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchCampaignCoverage(campaign.id)
      .then((data) => {
        if (cancelled) return;
        setCoverage(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : 'Не удалось загрузить покрытие');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // completed_assessments в зависимостях — перечитать покрытие после того,
    // как кто-то из учеников/учителей завершил анкету. campaign.id меняться
    // здесь не может — родитель монтирует панель заново через key={campaign.id},
    // сброс loading/error/coverage к начальным значениям делает сам ремоунт.
  }, [campaign.id, campaign.completed_assessments]);

  const handleClose = async () => {
    setError(null);
    setClosing(true);
    try {
      await closeCampaign(campaign.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось закрыть кампанию');
    } finally {
      setClosing(false);
    }
  };

  const handleReopen = async () => {
    setError(null);
    setReopening(true);
    try {
      await reopenCampaign(campaign.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось возобновить кампанию');
    } finally {
      setReopening(false);
    }
  };

  return (
    <Panel
      title={`Покрытие по классам · ${formatPeriod(campaign.period_year, campaign.period_month)}`}
      className="campaign-coverage"
    >
      <div className="campaign-coverage__head">
        <span className="campaign-coverage__total">
          {coverage ? `${coverage.completed} из ${coverage.total} анкет` : '—'}
        </span>
        {campaign.status === 'active' && (
          <Button variant="secondary" onClick={handleClose} disabled={closing}>
            {closing ? 'Закрываем…' : 'Закрыть кампанию'}
          </Button>
        )}
        {campaign.status === 'closed' && (
          <Button variant="secondary" onClick={handleReopen} disabled={reopening}>
            {reopening ? 'Возобновляем…' : 'Возобновить кампанию'}
          </Button>
        )}
      </div>

      {error && <div className="form-error">{error}</div>}

      {loading ? (
        <div className="admin-empty">Загрузка…</div>
      ) : !coverage || coverage.classes.length === 0 ? (
        <div className="admin-empty">Анкеты ещё не сгенерированы</div>
      ) : (
        <div className="coverage-rows">
          {coverage.classes.map((row) => (
            <div className="coverage-row" key={row.class_id ?? 'none'}>
              <div className="coverage-row__label">{row.class_label ?? 'без класса'}</div>
              <ProgressBar value={row.percent} className="coverage-row__bar" />
              <div className="coverage-row__counts">
                {row.completed} из {row.total}
              </div>
              <div className="coverage-row__pct">{Math.round(row.percent)}%</div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function GeneratePanel({
  campaign,
  allClasses,
  onGenerated,
}: {
  campaign: CampaignListItem;
  allClasses: SchoolClass[];
  onGenerated: () => void;
}) {
  const [checkedClassIds, setCheckedClassIds] = useState<Set<number>>(new Set());
  // Выбор учителей ПО КЛАССУ: ученика оценивают 2–4 учителя, а не весь
  // педсостав. Ключ появляется, только когда класс отмечен, — отправляем
  // ровно то, что админ видел на экране.
  const [teachersByClass, setTeachersByClass] = useState<Record<number, Set<number>>>({});
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const toggleClass = (id: number) => {
    setResult(null);
    setCheckedClassIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setTeachersByClass((prev) => {
      if (prev[id]) return prev;
      // По умолчанию — никого: 2–4 учителя выбирает человек, а молчаливое
      // «все 11» ровно та ситуация, от которой уходим.
      return { ...prev, [id]: new Set<number>() };
    });
  };

  const toggleTeacher = (classId: number, teacherId: number) => {
    setResult(null);
    setTeachersByClass((prev) => {
      const next = new Set(prev[classId] ?? []);
      if (next.has(teacherId)) next.delete(teacherId);
      else next.add(teacherId);
      return { ...prev, [classId]: next };
    });
  };

  const checkedClasses = allClasses.filter((c) => checkedClassIds.has(c.id));
  const withoutTeachers = checkedClasses.filter((c) => (teachersByClass[c.id]?.size ?? 0) === 0);
  const overLimit = checkedClasses.filter((c) => (teachersByClass[c.id]?.size ?? 0) > 4);

  const handleGenerate = async () => {
    if (checkedClassIds.size === 0) return;
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const payload: Record<number, number[]> = {};
      for (const id of checkedClassIds) payload[id] = [...(teachersByClass[id] ?? [])];
      const res = await generateAssessments(campaign.id, [...checkedClassIds], payload);
      setResult(
        res.created > 0
          ? `Добавлено новых анкет: ${res.created}`
          : 'Новых анкет не добавлено — все пары уже сгенерированы',
      );
      onGenerated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сгенерировать анкеты');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Panel title="Кто кого оценивает" className="campaign-generate">
      <div className="rater-rules">
        <div className="rater-rule">
          <div className="rater-rule__text">
            <div className="rater-rule__label">Самооценка</div>
            <div className="rater-rule__note">Каждый ученик оценивает себя</div>
          </div>
          <span className="rater-rule__badge">Всегда</span>
        </div>
        <div className="rater-rule">
          <div className="rater-rule__text">
            <div className="rater-rule__label">Родители</div>
            <div className="rater-rule__note">Только своего ребёнка</div>
          </div>
          <span className="rater-rule__badge">Всегда</span>
        </div>
        <div className="rater-rule">
          <div className="rater-rule__text">
            <div className="rater-rule__label">Учителя</div>
            <div className="rater-rule__note">
              Выбранные ниже — они оценивают всех учеников своего класса
            </div>
          </div>
          <span className="rater-rule__badge">По выбору</span>
        </div>
      </div>

      <div className="class-picker">
        <div className="class-picker__label">Классы и учителя-оценщики</div>
        {allClasses.length === 0 ? (
          <div className="admin-empty">Классов пока нет</div>
        ) : (
          <div className="assign-list">
            {allClasses.map((c) => (
              <div key={c.id}>
                <label className="assign-item">
                  <input
                    type="checkbox"
                    checked={checkedClassIds.has(c.id)}
                    onChange={() => toggleClass(c.id)}
                  />
                  <span className="assign-item__name">{classLabel(c)}</span>
                  <span className="assign-item__email">{c.students.length} учеников</span>
                </label>

                {checkedClassIds.has(c.id) && (
                  <div className="teacher-picker">
                    <div className="teacher-picker__hint">
                      Кто из учителей оценивает класс — обычно 2–4 человека
                    </div>
                    {c.teachers.length === 0 ? (
                      <div className="admin-empty">К классу не привязан ни один учитель</div>
                    ) : (
                      c.teachers.map((link) => (
                        <label key={link.teacher.id} className="teacher-picker__item">
                          <input
                            type="checkbox"
                            checked={teachersByClass[c.id]?.has(link.teacher.id) ?? false}
                            onChange={() => toggleTeacher(c.id, link.teacher.id)}
                          />
                          <span className="teacher-picker__name">{link.teacher.full_name}</span>
                          <span className="teacher-picker__role">
                            {link.is_homeroom ? 'кл. рук.' : (link.subject ?? '')}
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Не блокируем генерацию: 2–4 — это практика школы, а не инвариант. */}
      {overLimit.length > 0 && (
        <div className="campaign-generate__warning">
          Больше 4 учителей на класс ({overLimit.map(classLabel).join(', ')}) — обычно берут 2–4.
          Сгенерировать всё равно можно.
        </div>
      )}
      {withoutTeachers.length > 0 && (
        <div className="campaign-generate__warning">
          Учителя не выбраны ({withoutTeachers.map(classLabel).join(', ')}) — по этим классам
          будут только самооценка и анкеты родителей.
        </div>
      )}

      {error && <div className="form-error">{error}</div>}
      {result && !error && <div className="campaign-generate__result">{result}</div>}

      <Button block onClick={handleGenerate} disabled={submitting || checkedClassIds.size === 0}>
        {submitting ? 'Генерируем…' : 'Сгенерировать анкеты'}
      </Button>
    </Panel>
  );
}

function CreateCampaignModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const now = new Date();
  const [title, setTitle] = useState('');
  // Период — выбор из списка, а не свободный текст: ярлык-опечатка
  // («2026-е2е») раньше ломал резолюцию «последней кампании» у всей школы.
  const [periodYear, setPeriodYear] = useState(now.getFullYear());
  const [periodMonth, setPeriodMonth] = useState(now.getMonth() + 1);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = title.trim().length > 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      const payload: CreateCampaignIn = {
        title: title.trim(),
        period_year: periodYear,
        period_month: periodMonth,
      };
      const campaign = await createCampaign(payload);
      onCreated(campaign.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось создать кампанию');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal title="Новая кампания" onClose={onClose}>
      <label className="form-field">
        <span>Название</span>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Диагностика 360 · июнь 2026"
          autoFocus
        />
      </label>
      <div className="form-row">
        <label className="form-field">
          <span>Месяц</span>
          <select value={periodMonth} onChange={(e) => setPeriodMonth(Number(e.target.value))}>
            {MONTH_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Год</span>
          <input
            type="number"
            min={2000}
            max={2100}
            value={periodYear}
            onChange={(e) => setPeriodYear(Number(e.target.value))}
          />
        </label>
      </div>

      {error && <div className="form-error">{error}</div>}

      <div className="modal__actions">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button onClick={handleSubmit} disabled={submitting || !canSubmit}>
          {submitting ? 'Создаём…' : 'Создать кампанию'}
        </Button>
      </div>
    </Modal>
  );
}
