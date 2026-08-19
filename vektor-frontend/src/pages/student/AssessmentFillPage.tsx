import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../../components/layout/AppShell';
import { STUDENT_NAV_ITEMS } from '../../data/navigation';
import { Panel } from '../../components/ui/Panel';
import { Icon } from '../../components/icons/Icon';
import { ChapterPills } from '../../components/assessment/ChapterPills';
import { FocusQuestion } from '../../components/assessment/FocusQuestion';
import { DenseChapters } from '../../components/assessment/DenseChapters';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABELS } from '../../types/auth';
import { ApiError } from '../../api/client';
import { fetchAssessment, submitAnswers } from '../../api/assessments';
import { fetchCompetencies } from '../../api/competencies';
import type { AssessmentDetail } from '../../types/assessment';
import {
  firstIndexOfChapter,
  groupQuestionsIntoChapters,
  locateInChapters,
  type Chapter,
} from './assessmentGrouping';
import './AssessmentFillPage.css';

type ViewMode = 'focus' | 'dense';

/**
 * Экран прохождения анкеты 360 — открывается по клику «Заполнить»/«Продолжить»
 * с дашборда (StudentHome). Вопросы группируются по «ОР / навык» (см.
 * assessmentGrouping.ts), ответы сохраняются по одному сразу при выборе —
 * bulk-эндпоинт (submit_answers, Этап 4d) принимает частичные пачки и
 * upsert'ит, так что «одна кнопка Сохранить» не нужна: последний ответ,
 * закрывающий анкету, сам переводит статус в completed и уводит на дашборд.
 */
export function AssessmentFillPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const assessmentId = Number(id);

  const [detail, setDetail] = useState<AssessmentDetail | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [mode, setMode] = useState<ViewMode>('focus');
  const [activeIndex, setActiveIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pendingSaves, setPendingSaves] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAssessment(assessmentId), fetchCompetencies()])
      .then(([assessmentDetail, competencies]) => {
        if (cancelled) return;
        const builtChapters = groupQuestionsIntoChapters(assessmentDetail.questions, competencies);
        const initialAnswers: Record<number, number> = {};
        for (const q of assessmentDetail.questions) {
          if (q.value !== null) initialAnswers[q.id] = q.value;
        }
        const flat = builtChapters.flatMap((c) => c.questions);
        const firstUnanswered = flat.findIndex((q) => initialAnswers[q.id] === undefined);
        const startIndex = flat.length === 0 ? 0 : firstUnanswered === -1 ? flat.length - 1 : firstUnanswered;

        setDetail(assessmentDetail);
        setChapters(builtChapters);
        setAnswers(initialAnswers);
        setActiveIndex(startIndex);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить анкету');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assessmentId]);

  const flat = useMemo(() => chapters.flatMap((c) => c.questions), [chapters]);
  const totalCount = flat.length;
  const answeredCount = flat.filter((q) => answers[q.id] !== undefined).length;
  const location = locateInChapters(chapters, activeIndex);
  const currentChapter = chapters[location.chapterIndex];
  const currentQuestion = flat[activeIndex];

  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const answerQuestion = (questionId: number, value: number, advance: boolean) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
    setSaveError(null);
    setPendingSaves((n) => n + 1);
    submitAnswers(assessmentId, [{ question_id: questionId, value }])
      .then((result) => {
        if (result.status === 'completed') navigate('/');
      })
      .catch((err: unknown) => {
        setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить ответ');
      })
      .finally(() => setPendingSaves((n) => n - 1));

    if (advance) {
      setActiveIndex((idx) => (idx < flat.length - 1 ? idx + 1 : idx));
    }
  };

  const selectChapter = (outcomeAreaId: number) => {
    const chapterIndex = chapters.findIndex((c) => c.outcomeAreaId === outcomeAreaId);
    if (chapterIndex === -1) return;
    setActiveIndex(firstIndexOfChapter(chapters, chapterIndex, answers));
  };

  const stepChapter = (direction: 1 | -1) => {
    const target = location.chapterIndex + direction;
    if (target < 0 || target >= chapters.length) return;
    setActiveIndex(firstIndexOfChapter(chapters, target, answers));
  };

  const aboutLine =
    detail?.rater_role === 'self' ? 'Самооценка' : `Оценка: ${detail?.subject.full_name ?? ''}`;

  return (
    <AppShell
      navItems={STUDENT_NAV_ITEMS}
      activeNavKey="surveys"
      userFullName={user.full_name}
      userRoleLabel={ROLE_LABELS[user.role]}
      onLogout={logout}
    >
      <button type="button" className="assessment-fill__back" onClick={() => navigate('/')}>
        <Icon name="arrowLeft" size={16} />
        На главную
      </button>

      {loading ? (
        <Panel>
          <div className="app-main__sub">Загрузка…</div>
        </Panel>
      ) : loadError ? (
        <Panel>
          <div className="form-error">{loadError}</div>
        </Panel>
      ) : detail && totalCount > 0 ? (
        <>
          <div className="assessment-fill__head">
            <div>
              <h2>{detail.campaign_title}</h2>
              <div className="assessment-fill__subject">
                <Icon name="user" size={13} />
                {aboutLine}
              </div>
            </div>
            <div className="assessment-fill__mode">
              <button
                type="button"
                className={mode === 'focus' ? 'assessment-fill__mode-btn--active' : ''}
                onClick={() => setMode('focus')}
              >
                Фокус · по одному
              </button>
              <button
                type="button"
                className={mode === 'dense' ? 'assessment-fill__mode-btn--active' : ''}
                onClick={() => setMode('dense')}
              >
                Лента · главой
              </button>
            </div>
          </div>

          {detail.rater_role === 'peer' && (
            <div className="assessment-fill__peer-banner">
              <Icon name="shieldLock" size={17} />
              <div>
                Твои ответы одноклассник увидит только вместе с ответами других — по отдельности
                никогда. Если оценок в группе окажется меньше трёх, балл вообще не покажут: так
                нельзя вычислить, кто что поставил.
              </div>
            </div>
          )}

          <ChapterPills
            chapters={chapters.map((c) => ({
              outcomeAreaId: c.outcomeAreaId,
              name: c.name,
              answered: c.questions.filter((q) => answers[q.id] !== undefined).length,
              total: c.questions.length,
            }))}
            activeChapterId={currentChapter?.outcomeAreaId}
            onSelect={selectChapter}
            answeredCount={answeredCount}
            totalCount={totalCount}
          />

          {saveError && <div className="form-error assessment-fill__save-error">{saveError}</div>}

          {mode === 'focus' && currentChapter && currentQuestion ? (
            <FocusQuestion
              chapterName={currentChapter.name}
              chapterNum={location.chapterIndex + 1}
              chapterCount={chapters.length}
              qNumInChapter={location.indexInChapter + 1}
              qTotalInChapter={currentChapter.questions.length}
              aboutLine={aboutLine}
              questionText={currentQuestion.text}
              value={answers[currentQuestion.id]}
              onSelect={(value) => answerQuestion(currentQuestion.id, value, true)}
              onBack={() => setActiveIndex((idx) => Math.max(0, idx - 1))}
              onSkip={() => setActiveIndex((idx) => Math.min(flat.length - 1, idx + 1))}
              canGoBack={activeIndex > 0}
              canSkip={activeIndex < flat.length - 1}
              questionKey={currentQuestion.id}
            />
          ) : mode === 'dense' && currentChapter ? (
            <DenseChapters
              chapters={chapters}
              activeChapterId={currentChapter.outcomeAreaId}
              onSelectChapter={selectChapter}
              answers={answers}
              onAnswer={(questionId, value) => answerQuestion(questionId, value, false)}
              onPrevChapter={() => stepChapter(-1)}
              onNextChapter={() => stepChapter(1)}
              hasPrevChapter={location.chapterIndex > 0}
              hasNextChapter={location.chapterIndex < chapters.length - 1}
            />
          ) : null}

          <div className="assessment-fill__status">
            {pendingSaves > 0 ? (
              'Сохраняем…'
            ) : (
              <>
                <Icon name="check" size={13} />
                Сохранено
              </>
            )}
          </div>
        </>
      ) : (
        <Panel>
          <div className="app-main__sub">Нет вопросов, доступных для заполнения</div>
        </Panel>
      )}
    </AppShell>
  );
}
