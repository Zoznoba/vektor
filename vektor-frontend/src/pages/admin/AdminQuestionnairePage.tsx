import { useCallback, useEffect, useState } from 'react';
import { AdminShell } from './AdminShell';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Icon } from '../../components/icons/Icon';
import { useApi } from '../../hooks/useApi';
import { ApiError } from '../../api/client';
import {
  fetchQuestionnaireVersions,
  createDraftVersion,
  fetchQuestionnaireTree,
  publishVersion,
  discardDraft,
  addOutcomeArea,
  updateOutcomeArea,
  archiveOutcomeArea,
  moveOutcomeArea,
  addCompetency,
  updateCompetency,
  archiveCompetency,
  moveCompetency,
  addQuestion,
  updateQuestion,
  deleteQuestion,
  moveQuestion,
} from '../../api/questionnaireBuilder';
import type {
  BuilderCompetency,
  BuilderOutcomeArea,
  QuestionnaireTree,
} from '../../types/questionnaireBuilder';
import './admin.css';
import './questionnaire-builder.css';

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

/**
 * Конструктор анкеты: главы («ОР / навык») → критерии → вопросы. Структуру
 * можно менять только внутри черновика (draft) — опубликованная редакция
 * заморожена, чтобы не поехала историческая аналитика по кампаниям, которые
 * её уже используют (см. VersionNotDraft в competencies/service.py).
 */
export function AdminQuestionnairePage() {
  const versions = useApi(fetchQuestionnaireVersions);
  const [tree, setTree] = useState<QuestionnaireTree | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const current = versions.data?.find((v) => v.is_current) ?? null;
  const draft = versions.data?.find((v) => v.status === 'draft') ?? null;

  const reloadTree = useCallback((versionId: number) => {
    setTreeLoading(true);
    setTreeError(null);
    fetchQuestionnaireTree(versionId)
      .then((data) => setTree(data))
      .catch((err: unknown) => setTreeError(errorMessage(err, 'Не удалось загрузить анкету')))
      .finally(() => setTreeLoading(false));
  }, []);

  useEffect(() => {
    if (draft) reloadTree(draft.id);
    else setTree(null);
  }, [draft?.id, reloadTree]);

  const handleCreateDraft = async () => {
    setActionError(null);
    setBusy(true);
    try {
      await createDraftVersion();
      versions.reload();
    } catch (err) {
      setActionError(errorMessage(err, 'Не удалось создать черновик'));
    } finally {
      setBusy(false);
    }
  };

  const handlePublish = async () => {
    if (!draft) return;
    if (
      !window.confirm(
        'Опубликовать черновик? Новые кампании будут создаваться по этой редакции — ' +
          'после публикации редактирование станет недоступно.',
      )
    ) {
      return;
    }
    setActionError(null);
    setBusy(true);
    try {
      await publishVersion(draft.id);
      versions.reload();
    } catch (err) {
      setActionError(errorMessage(err, 'Не удалось опубликовать анкету'));
    } finally {
      setBusy(false);
    }
  };

  const handleDiscard = async () => {
    if (!draft) return;
    if (!window.confirm('Отменить черновик? Все изменения будут потеряны безвозвратно.')) return;
    setActionError(null);
    setBusy(true);
    try {
      await discardDraft(draft.id);
      versions.reload();
    } catch (err) {
      setActionError(errorMessage(err, 'Не удалось отменить черновик'));
    } finally {
      setBusy(false);
    }
  };

  const onChanged = () => {
    if (draft) reloadTree(draft.id);
  };

  return (
    <AdminShell activeNavKey="tests">
      <div className="admin-toolbar">
        <h2>Конструктор анкеты</h2>
      </div>

      {versions.error && <div className="form-error">{versions.error}</div>}

      <Panel title="Действующая редакция" className="qb-current-panel">
        {versions.loading ? (
          <div className="admin-empty">Загрузка…</div>
        ) : current ? (
          <div className="qb-current">
            <div className="qb-current__title">{current.title}</div>
            <div className="qb-current__meta">
              Код {current.code} · опубликована{' '}
              {new Date(current.created_at).toLocaleDateString('ru-RU')}
            </div>
          </div>
        ) : (
          <div className="admin-empty">Нет действующей редакции</div>
        )}
      </Panel>

      {actionError && <div className="form-error">{actionError}</div>}

      {!versions.loading && !draft && (
        <Panel className="qb-draft-cta">
          <div className="qb-draft-cta__text">
            Чтобы изменить главы, критерии или вопросы анкеты, сначала создайте черновик —
            редактирование не затронет действующую редакцию и уже запущенные кампании, пока вы
            его не опубликуете.
          </div>
          <Button onClick={handleCreateDraft} disabled={busy}>
            <Icon name="plus" size={15} />
            Создать черновик для редактирования
          </Button>
        </Panel>
      )}

      {draft && (
        <>
          <Panel className="qb-draft-toolbar">
            <div className="qb-draft-toolbar__info">
              <Badge variant="amber">Черновик</Badge>
              <span>{draft.title}</span>
            </div>
            <div className="qb-draft-toolbar__actions">
              <Button variant="secondary" onClick={handleDiscard} disabled={busy}>
                Отменить черновик
              </Button>
              <Button onClick={handlePublish} disabled={busy}>
                Опубликовать
              </Button>
            </div>
          </Panel>

          {treeError && <div className="form-error">{treeError}</div>}

          {treeLoading && !tree ? (
            <Panel>
              <div className="admin-empty">Загрузка…</div>
            </Panel>
          ) : (
            tree && <QuestionnaireTreeEditor tree={tree} versionId={draft.id} onChanged={onChanged} />
          )}
        </>
      )}
    </AdminShell>
  );
}

function QuestionnaireTreeEditor({
  tree,
  versionId,
  onChanged,
}: {
  tree: QuestionnaireTree;
  versionId: number;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const sortedAreas = [...tree.outcome_areas].sort((a, b) => a.order - b.order);

  return (
    <Panel>
      <div className="qb-tree">
        {error && <div className="form-error">{error}</div>}
        {sortedAreas.length === 0 && (
          <div className="admin-empty">Глав пока нет — добавьте первую ниже</div>
        )}
        {sortedAreas.map((area, index) => (
          <OutcomeAreaCard
            key={area.id}
            area={area}
            versionId={versionId}
            isFirst={index === 0}
            isLast={index === sortedAreas.length - 1}
            onChanged={onChanged}
            onError={setError}
          />
        ))}
        <InlineAddForm
          placeholder="Название главы"
          buttonLabel="Добавить главу"
          onSubmit={async (name) => {
            try {
              await addOutcomeArea(versionId, name);
              onChanged();
            } catch (err) {
              setError(errorMessage(err, 'Не удалось добавить главу'));
            }
          }}
        />
      </div>
    </Panel>
  );
}

function OutcomeAreaCard({
  area,
  versionId,
  isFirst,
  isLast,
  onChanged,
  onError,
}: {
  area: BuilderOutcomeArea;
  versionId: number;
  isFirst: boolean;
  isLast: boolean;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState(area.name);
  const [collapsed, setCollapsed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => setName(area.name), [area.name]);

  const run = async (fn: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (err) {
      onError(errorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const handleNameBlur = () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === area.name) {
      setName(area.name);
      return;
    }
    run(() => updateOutcomeArea(area.id, trimmed), 'Не удалось переименовать главу');
  };

  const sortedCompetencies = [...area.competencies].sort((a, b) => a.order - b.order);

  return (
    <div className={`qb-area ${area.is_archived ? 'qb-area--archived' : ''}`.trim()}>
      <div className="qb-area__head">
        <button
          className="qb-collapse"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? 'Развернуть' : 'Свернуть'}
        >
          <Icon name={collapsed ? 'arrowRight' : 'chevronDown'} size={15} />
        </button>
        <input
          className="qb-area__name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={handleNameBlur}
          disabled={busy}
        />
        {area.is_draft && <Badge variant="blue">новая</Badge>}
        {area.is_archived && <Badge variant="gray">архив</Badge>}
        <div className="qb-area__spacer" />
        <div className="qb-move-buttons">
          <button
            disabled={isFirst || busy}
            onClick={() => run(() => moveOutcomeArea(area.id, 'up'), 'Не удалось переместить главу')}
            aria-label="Выше"
          >
            <Icon name="arrowUp" size={13} />
          </button>
          <button
            disabled={isLast || busy}
            onClick={() => run(() => moveOutcomeArea(area.id, 'down'), 'Не удалось переместить главу')}
            aria-label="Ниже"
          >
            <Icon name="arrowDown" size={13} />
          </button>
        </div>
        <button
          className="qb-archive-btn"
          disabled={busy}
          onClick={() =>
            run(
              () => archiveOutcomeArea(area.id, !area.is_archived),
              'Не удалось изменить статус главы',
            )
          }
        >
          <Icon name="archive" size={13} />
          {area.is_archived ? 'Восстановить' : 'В архив'}
        </button>
      </div>

      {!collapsed && (
        <div className="qb-area__body">
          {sortedCompetencies.length === 0 && (
            <div className="admin-empty">Критериев пока нет</div>
          )}
          {sortedCompetencies.map((comp, index) => (
            <CompetencyCard
              key={comp.id}
              competency={comp}
              versionId={versionId}
              isFirst={index === 0}
              isLast={index === sortedCompetencies.length - 1}
              onChanged={onChanged}
              onError={onError}
            />
          ))}
          <AddCompetencyForm
            versionId={versionId}
            areaId={area.id}
            onAdded={onChanged}
            onError={onError}
          />
        </div>
      )}
    </div>
  );
}

function CompetencyCard({
  competency,
  versionId,
  isFirst,
  isLast,
  onChanged,
  onError,
}: {
  competency: BuilderCompetency;
  versionId: number;
  isFirst: boolean;
  isLast: boolean;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState(competency.name);
  const [description, setDescription] = useState(competency.description ?? '');
  const [minGrade, setMinGrade] = useState(competency.min_grade?.toString() ?? '');
  const [maxGrade, setMaxGrade] = useState(competency.max_grade?.toString() ?? '');
  const [busy, setBusy] = useState(false);

  useEffect(() => setName(competency.name), [competency.name]);
  useEffect(() => setDescription(competency.description ?? ''), [competency.description]);
  useEffect(() => setMinGrade(competency.min_grade?.toString() ?? ''), [competency.min_grade]);
  useEffect(() => setMaxGrade(competency.max_grade?.toString() ?? ''), [competency.max_grade]);

  const run = async (fn: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (err) {
      onError(errorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const saveFields = () => {
    const trimmedName = name.trim();
    const trimmedDescription = description.trim();
    const min = minGrade.trim() ? Number(minGrade) : null;
    const max = maxGrade.trim() ? Number(maxGrade) : null;
    const unchanged =
      trimmedName === competency.name &&
      trimmedDescription === (competency.description ?? '') &&
      min === competency.min_grade &&
      max === competency.max_grade;
    if (!trimmedName || unchanged) {
      setName(competency.name);
      return;
    }
    run(
      () =>
        updateCompetency(competency.id, {
          name: trimmedName,
          description: trimmedDescription || null,
          min_grade: min,
          max_grade: max,
        }),
      'Не удалось сохранить критерий',
    );
  };

  const sortedQuestions = [...competency.questions].sort((a, b) => a.order - b.order);

  return (
    <div className={`qb-competency ${competency.is_archived ? 'qb-competency--archived' : ''}`.trim()}>
      <div className="qb-competency__head">
        <input
          className="qb-competency__name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={saveFields}
          disabled={busy}
        />
        {competency.is_draft && <Badge variant="blue">новый</Badge>}
        {competency.is_archived && <Badge variant="gray">архив</Badge>}
        <div className="qb-move-buttons">
          <button
            disabled={isFirst || busy}
            onClick={() =>
              run(() => moveCompetency(competency.id, 'up'), 'Не удалось переместить критерий')
            }
            aria-label="Выше"
          >
            <Icon name="arrowUp" size={13} />
          </button>
          <button
            disabled={isLast || busy}
            onClick={() =>
              run(() => moveCompetency(competency.id, 'down'), 'Не удалось переместить критерий')
            }
            aria-label="Ниже"
          >
            <Icon name="arrowDown" size={13} />
          </button>
        </div>
        <button
          className="qb-archive-btn"
          disabled={busy}
          onClick={() =>
            run(
              () => archiveCompetency(competency.id, !competency.is_archived),
              'Не удалось изменить статус критерия',
            )
          }
        >
          <Icon name="archive" size={13} />
          {competency.is_archived ? 'Восстановить' : 'В архив'}
        </button>
      </div>

      <div className="qb-competency__fields">
        <input
          className="qb-competency__description"
          value={description}
          placeholder="Описание (необязательно)"
          onChange={(e) => setDescription(e.target.value)}
          onBlur={saveFields}
          disabled={busy}
        />
        <label className="qb-grade-field">
          С класса
          <input
            type="number"
            min={1}
            max={11}
            value={minGrade}
            onChange={(e) => setMinGrade(e.target.value)}
            onBlur={saveFields}
            disabled={busy}
          />
        </label>
        <label className="qb-grade-field">
          По класс
          <input
            type="number"
            min={1}
            max={11}
            value={maxGrade}
            onChange={(e) => setMaxGrade(e.target.value)}
            onBlur={saveFields}
            disabled={busy}
          />
        </label>
      </div>

      <div className="qb-questions">
        {sortedQuestions.map((q, index) => (
          <QuestionRow
            key={q.id}
            question={q}
            isFirst={index === 0}
            isLast={index === sortedQuestions.length - 1}
            onChanged={onChanged}
            onError={onError}
          />
        ))}
        <InlineAddForm
          placeholder="Текст вопроса"
          buttonLabel="Добавить вопрос"
          onSubmit={async (text) => {
            try {
              await addQuestion(versionId, competency.id, text);
              onChanged();
            } catch (err) {
              onError(errorMessage(err, 'Не удалось добавить вопрос'));
            }
          }}
        />
      </div>
    </div>
  );
}

function QuestionRow({
  question,
  isFirst,
  isLast,
  onChanged,
  onError,
}: {
  question: { id: number; text: string; order: number };
  isFirst: boolean;
  isLast: boolean;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [text, setText] = useState(question.text);
  const [busy, setBusy] = useState(false);

  useEffect(() => setText(question.text), [question.text]);

  const run = async (fn: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (err) {
      onError(errorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  };

  const handleBlur = () => {
    const trimmed = text.trim();
    if (!trimmed || trimmed === question.text) {
      setText(question.text);
      return;
    }
    run(() => updateQuestion(question.id, trimmed), 'Не удалось изменить вопрос');
  };

  const handleDelete = () => {
    if (!window.confirm('Удалить вопрос из черновика?')) return;
    run(() => deleteQuestion(question.id), 'Не удалось удалить вопрос');
  };

  return (
    <div className="qb-question">
      <div className="qb-move-buttons">
        <button
          disabled={isFirst || busy}
          onClick={() => run(() => moveQuestion(question.id, 'up'), 'Не удалось переместить вопрос')}
          aria-label="Выше"
        >
          <Icon name="arrowUp" size={12} />
        </button>
        <button
          disabled={isLast || busy}
          onClick={() =>
            run(() => moveQuestion(question.id, 'down'), 'Не удалось переместить вопрос')
          }
          aria-label="Ниже"
        >
          <Icon name="arrowDown" size={12} />
        </button>
      </div>
      <input
        className="qb-question__text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={handleBlur}
        disabled={busy}
      />
      <button className="qb-delete-btn" disabled={busy} onClick={handleDelete} aria-label="Удалить вопрос">
        <Icon name="trash" size={13} />
      </button>
    </div>
  );
}

function AddCompetencyForm({
  versionId,
  areaId,
  onAdded,
  onError,
}: {
  versionId: number;
  areaId: number;
  onAdded: () => void;
  onError: (msg: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [minGrade, setMinGrade] = useState('');
  const [maxGrade, setMaxGrade] = useState('');
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button className="qb-add-trigger" onClick={() => setOpen(true)}>
        <Icon name="plus" size={12} /> Добавить критерий
      </button>
    );
  }

  const reset = () => {
    setOpen(false);
    setName('');
    setDescription('');
    setMinGrade('');
    setMaxGrade('');
  };

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await addCompetency(versionId, areaId, {
        name: trimmed,
        description: description.trim() || null,
        min_grade: minGrade.trim() ? Number(minGrade) : null,
        max_grade: maxGrade.trim() ? Number(maxGrade) : null,
      });
      onAdded();
      reset();
    } catch (err) {
      onError(errorMessage(err, 'Не удалось добавить критерий'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="qb-add-form-competency">
      <input
        autoFocus
        placeholder="Название критерия"
        value={name}
        onChange={(e) => setName(e.target.value)}
        disabled={busy}
      />
      <div className="qb-add-form-competency__row">
        <input
          placeholder="Описание (необязательно)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={busy}
          style={{ flex: 1, minWidth: 160 }}
        />
        <label className="qb-grade-field">
          С класса
          <input
            type="number"
            min={1}
            max={11}
            value={minGrade}
            onChange={(e) => setMinGrade(e.target.value)}
            disabled={busy}
          />
        </label>
        <label className="qb-grade-field">
          По класс
          <input
            type="number"
            min={1}
            max={11}
            value={maxGrade}
            onChange={(e) => setMaxGrade(e.target.value)}
            disabled={busy}
          />
        </label>
      </div>
      <div className="qb-add-form-competency__actions">
        <Button onClick={submit} disabled={busy || !name.trim()}>
          Добавить
        </Button>
        <Button variant="secondary" onClick={reset} disabled={busy}>
          Отмена
        </Button>
      </div>
    </div>
  );
}

function InlineAddForm({
  placeholder,
  buttonLabel,
  onSubmit,
}: {
  placeholder: string;
  buttonLabel: string;
  onSubmit: (value: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button className="qb-add-trigger" onClick={() => setOpen(true)}>
        <Icon name="plus" size={12} /> {buttonLabel}
      </button>
    );
  }

  const submit = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await onSubmit(trimmed);
      setValue('');
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="qb-add-form">
      <input
        autoFocus
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
        disabled={busy}
      />
      <Button onClick={submit} disabled={busy || !value.trim()}>
        Добавить
      </Button>
      <Button
        variant="secondary"
        onClick={() => {
          setOpen(false);
          setValue('');
        }}
        disabled={busy}
      >
        Отмена
      </Button>
    </div>
  );
}
