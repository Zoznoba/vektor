import { useEffect, useMemo, useState } from 'react';
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
        <Button onClick={() => setShowCreate(true)}>
          <Icon name="plus" size={15} />
          Новая кампания
        </Button>
      </div>

      {campaigns.error && <div className="form-error">{campaigns.error}</div>}

      {campaigns.loading ? (
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
                  <span className="campaign-card__period">{c.period}</span>
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
    <Panel title={`Покрытие по классам · ${campaign.period}`} className="campaign-coverage">
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
  const [includePeers, setIncludePeers] = useState(false);
  const [checkedClassIds, setCheckedClassIds] = useState<Set<number>>(new Set());
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
  };

  const handleGenerate = async () => {
    if (checkedClassIds.size === 0) return;
    setError(null);
    setResult(null);
    setSubmitting(true);
    try {
      const res = await generateAssessments(campaign.id, [...checkedClassIds], includePeers);
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
            <div className="rater-rule__note">Каждый учитель класса</div>
          </div>
          <span className="rater-rule__badge">Всегда</span>
        </div>
        <label className="rater-rule rater-rule--toggle">
          <div className="rater-rule__text">
            <div className="rater-rule__label">Одноклассники</div>
            <div className="rater-rule__note">
              Оценивают друг друга — анонимно, раскрывается от 3 ответов
            </div>
          </div>
          <input
            type="checkbox"
            checked={includePeers}
            onChange={(e) => setIncludePeers(e.target.checked)}
          />
        </label>
      </div>

      <div className="class-picker">
        <div className="class-picker__label">Классы для генерации</div>
        {allClasses.length === 0 ? (
          <div className="admin-empty">Классов пока нет</div>
        ) : (
          <div className="assign-list">
            {allClasses.map((c) => (
              <label key={c.id} className="assign-item">
                <input
                  type="checkbox"
                  checked={checkedClassIds.has(c.id)}
                  onChange={() => toggleClass(c.id)}
                />
                <span className="assign-item__name">{classLabel(c)}</span>
                <span className="assign-item__email">{c.students.length} учеников</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <div className="form-error">{error}</div>}
      {result && !error && <div className="campaign-generate__result">{result}</div>}

      <Button
        block
        onClick={handleGenerate}
        disabled={submitting || checkedClassIds.size === 0}
      >
        {submitting ? 'Генерируем…' : 'Сгенерировать анкеты'}
      </Button>
      <div className="campaign-generate__hint">
        Повторный запуск добавит только новые пары — уже заполненные анкеты не тронет.
      </div>
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
  const [title, setTitle] = useState('');
  const [period, setPeriod] = useState('');
  const [opensAt, setOpensAt] = useState('');
  const [closesAt, setClosesAt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = title.trim().length > 0 && period.trim().length > 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      const payload: CreateCampaignIn = {
        title: title.trim(),
        period: period.trim(),
        opens_at: opensAt ? new Date(opensAt).toISOString() : null,
        closes_at: closesAt ? new Date(closesAt).toISOString() : null,
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
      <label className="form-field">
        <span>Период</span>
        <input
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          placeholder="2026-06"
          maxLength={20}
        />
      </label>
      <label className="form-field">
        <span>Открытие анкет (необязательно)</span>
        <input type="datetime-local" value={opensAt} onChange={(e) => setOpensAt(e.target.value)} />
      </label>
      <label className="form-field">
        <span>Дедлайн (необязательно)</span>
        <input
          type="datetime-local"
          value={closesAt}
          onChange={(e) => setClosesAt(e.target.value)}
        />
      </label>

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
