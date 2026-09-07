import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/icons/Icon';
import { useApi } from '../../hooks/useApi';
import { ApiError } from '../../api/client';
import {
  applyPromotion,
  fetchCurrentPromotion,
  previewPromotion,
  undoPromotion,
} from '../../api/promotion';
import type { PromotionPlan, PromotionRun, PromotionTransition } from '../../api/promotion';
import './promotion.css';

/**
 * Перевод всей школы на класс вперёд — раз в год. Экран показывает сухой
 * прогон (кто куда перейдёт, кто выпускается), даёт отредактировать целевую
 * секцию и снять перенос учителей, и применяет всё одной операцией под
 * подтверждение учебного года.
 *
 * Прошлая диагностика при переводе не меняется: результаты и динамика
 * считаются по снапшотам анкет, а не по текущему классу ученика.
 */
export function AdminPromotionPage() {
  const navigate = useNavigate();
  const current = useApi(fetchCurrentPromotion);

  // Локально применённый результат — показываем résumé сразу, не дожидаясь
  // повторной загрузки current.
  const [applied, setApplied] = useState<PromotionRun | null>(null);
  const run = applied ?? current.data;

  return (
    <AdminShell activeNavKey="classes">
      <div className="admin-toolbar">
        <button className="link-back" onClick={() => navigate('/admin/classes')}>
          <Icon name="arrowLeft" size={16} /> Классы
        </button>
        <h2>Перевод на новый учебный год</h2>
      </div>

      {current.loading && !current.data ? (
        <Panel>
          <div className="admin-empty">Загрузка…</div>
        </Panel>
      ) : run && !run.undone_at ? (
        <RunResume
          run={run}
          onUndone={(updated) => {
            setApplied(null);
            current.reload();
            void updated;
          }}
        />
      ) : (
        <PromotionPreview
          onApplied={(r) => {
            setApplied(r);
            current.reload();
          }}
        />
      )}
    </AdminShell>
  );
}

// ── résumé выполненного перевода ─────────────────────────────────────────

function RunResume({
  run,
  onUndone,
}: {
  run: PromotionRun;
  onUndone: (r: PromotionRun) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const undo = async () => {
    setBusy(true);
    setError(null);
    try {
      onUndone(await undoPromotion(run.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отменить перевод');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel>
      <div className="promotion-resume">
        <div className="promotion-resume__badge">
          <Icon name="check" size={20} />
        </div>
        <div>
          <h3>Перевод за {run.academic_year} выполнен</h3>
          <p className="promotion-resume__meta">
            {new Date(run.ran_at).toLocaleString('ru-RU', {
              day: 'numeric',
              month: 'long',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </p>
        </div>
      </div>

      <div className="promotion-metrics">
        <Metric value={run.summary.moved} label="переведено учеников" />
        <Metric value={run.summary.graduated} label="выпускников" />
        <Metric value={run.summary.classes_created} label="классов создано" />
      </div>

      {error && <div className="form-error">{error}</div>}

      <div className="promotion-actions">
        <Button variant="danger" onClick={undo} disabled={busy || !run.can_undo}>
          {busy ? 'Отмена…' : 'Отменить перевод'}
        </Button>
        {!run.can_undo && (
          <p className="promotion-hint">
            Откат недоступен: после перевода уже создана кампания, её состав нельзя
            менять задним числом.
          </p>
        )}
      </div>
    </Panel>
  );
}

// ── предпросмотр и запуск ────────────────────────────────────────────────

function PromotionPreview({ onApplied }: { onApplied: (r: PromotionRun) => void }) {
  // Переопределения целевой секции: source_class_id → секция. Меняют
  // группировку переходов, поэтому при изменении перезапрашиваем план.
  const [overrides, setOverrides] = useState<Record<number, string>>({});
  const load = useCallback(() => previewPromotion(overrides), [overrides]);
  const plan = useApi<PromotionPlan>(load);

  // Перенос учителей в новый целевой класс. По умолчанию включён для каждого
  // перехода без слияния, где целевой создаётся с нуля; carryOff хранит только
  // ручные снятия галочки — так не нужен эффект, синхронизирующий состояние с
  // приходящим планом.
  const [carryOff, setCarryOff] = useState<Record<number, boolean>>({});
  const carry = useMemo(() => {
    const on = new Set<number>();
    for (const t of plan.data?.transitions ?? []) {
      if (!t.merge && t.target_class_id === null) {
        const id = t.source_class_ids[0];
        if (!carryOff[id]) on.add(id);
      }
    }
    return on;
  }, [plan.data, carryOff]);

  const [confirmText, setConfirmText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = plan.data;
  const confirmed = data ? confirmText.trim() === data.academic_year : false;

  const setOverride = (sourceIds: number[], value: string) => {
    setOverrides((prev) => {
      const next = { ...prev };
      for (const id of sourceIds) next[id] = value;
      return next;
    });
  };

  const toggleCarry = (sourceId: number) => {
    setCarryOff((prev) => ({ ...prev, [sourceId]: !prev[sourceId] }));
  };

  const submit = async () => {
    if (!data || !confirmed) return;
    setBusy(true);
    setError(null);
    try {
      onApplied(
        await applyPromotion({
          confirmAcademicYear: data.academic_year,
          sectionOverrides: overrides,
          carryTeachersFor: [...carry],
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось выполнить перевод');
    } finally {
      setBusy(false);
    }
  };

  if (plan.loading && !data) {
    return (
      <Panel>
        <div className="admin-empty">Построение плана…</div>
      </Panel>
    );
  }
  if (plan.error || !data) {
    return (
      <Panel>
        <div className="form-error">{plan.error ?? 'Не удалось построить план'}</div>
      </Panel>
    );
  }

  const nothingToDo = data.transitions.length === 0 && data.graduating.length === 0;

  return (
    <>
      <Panel>
        <p className="promotion-lead">
          <strong>{data.academic_year}.</strong> Затрагивает {data.total_moving}{' '}
          {plural(data.total_moving, 'ученика', 'учеников', 'учеников')}, выпускается{' '}
          {data.total_graduating}, будет создано классов: {data.classes_to_create}.
        </p>
        <p className="promotion-hint">
          Членство в кейсах (кружках) и связи «родитель — ребёнок» перевод не меняет.
          Прошлая диагностика остаётся привязанной к прежнему классу.
        </p>

        {data.warnings.map((w) => (
          <div key={w} className="promotion-warning">
            <Icon name="bell" size={15} /> {w}
          </div>
        ))}
      </Panel>

      {nothingToDo && (
        <Panel>
          <div className="admin-empty">
            Переводить некого: в классах нет учеников либо школа состоит только из
            выпускных классов без состава.
          </div>
        </Panel>
      )}

      {data.transitions.length > 0 && (
        <Panel title="Переходы">
          <table className="admin-table promotion-table">
            <thead>
              <tr>
                <th>Класс</th>
                <th>Учеников</th>
                <th>Целевая секция</th>
                <th>Учителя</th>
              </tr>
            </thead>
            <tbody>
              {data.transitions.map((t) => (
                <TransitionRow
                  key={`${t.target_grade}-${t.target_section}-${t.source_class_ids.join(',')}`}
                  t={t}
                  carry={carry}
                  onToggleCarry={toggleCarry}
                  onSection={(value) => setOverride(t.source_class_ids, value)}
                  sectionValue={
                    overrides[t.source_class_ids[0]] ?? t.target_section
                  }
                />
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {data.graduating.length > 0 && (
        <Panel title="Выпуск">
          <table className="admin-table promotion-table">
            <tbody>
              {data.graduating.map((g) => (
                <tr key={g.class_id}>
                  <td>
                    {g.class_label} <Icon name="arrowRight" size={14} /> выпуск
                  </td>
                  <td>
                    {g.student_count}{' '}
                    {plural(g.student_count, 'ученик', 'ученика', 'учеников')} — деактивация
                    и открепление от класса
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {!nothingToDo && (
        <Panel>
          <label className="promotion-confirm">
            <span>
              Введите «<strong>{data.academic_year}</strong>» для подтверждения
            </span>
            <input
              className="admin-select"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={data.academic_year}
            />
          </label>

          {error && <div className="form-error">{error}</div>}

          <div className="promotion-actions">
            <Button onClick={submit} disabled={!confirmed || busy}>
              {busy
                ? 'Выполняется…'
                : `Выполнить перевод (${data.total_moving} ${plural(
                    data.total_moving,
                    'ученик',
                    'ученика',
                    'учеников',
                  )})`}
            </Button>
          </div>
        </Panel>
      )}
    </>
  );
}

function TransitionRow({
  t,
  carry,
  onToggleCarry,
  onSection,
  sectionValue,
}: {
  t: PromotionTransition;
  carry: Set<number>;
  onToggleCarry: (sourceId: number) => void;
  onSection: (value: string) => void;
  sectionValue: string;
}) {
  const canCarry = !t.merge && t.target_class_id === null;
  return (
    <tr>
      <td>
        <span className="promotion-flow">
          {t.source_labels.join(', ')} <Icon name="arrowRight" size={14} />{' '}
          <strong>{t.target_label}</strong>
          {t.target_class_id === null && <span className="promotion-tag">новый</span>}
          {t.merge && (
            <span className="promotion-tag promotion-tag--merge" title="Классы объединяются">
              слияние
            </span>
          )}
        </span>
      </td>
      <td>{t.moving_count}</td>
      <td>
        <input
          className="promotion-section-input"
          value={sectionValue}
          onChange={(e) => onSection(e.target.value)}
          aria-label="Целевая секция"
        />
      </td>
      <td>
        {canCarry ? (
          <label className="promotion-carry">
            <input
              type="checkbox"
              checked={carry.has(t.source_class_ids[0])}
              onChange={() => onToggleCarry(t.source_class_ids[0])}
            />
            перенести
          </label>
        ) : t.merge ? (
          <span className="promotion-muted">назначить вручную</span>
        ) : (
          <span className="promotion-muted">—</span>
        )}
      </td>
    </tr>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return (
    <div className="metric">
      <div className="metric__value">{value}</div>
      <div className="metric__label">{label}</div>
    </div>
  );
}

/** Русское склонение по числу: 1 ученик / 2 ученика / 5 учеников. */
function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}
