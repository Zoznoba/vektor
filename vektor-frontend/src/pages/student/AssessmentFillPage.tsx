import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../../components/layout/AppShell';
import { STUDENT_NAV_ITEMS } from '../../data/navigation';
import { Panel } from '../../components/ui/Panel';
import { Button } from '../../components/ui/Button';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { Icon } from '../../components/icons/Icon';
import { useAuth } from '../../auth/AuthContext';
import { ROLE_LABELS } from '../../types/auth';
import { ApiError } from '../../api/client';
import { fetchAssessment, submitAnswers } from '../../api/assessments';
import type { AssessmentDetail } from '../../types/assessment';
import './AssessmentFillPage.css';

const SCALE = [1, 2, 3, 4, 5];

/**
 * Экран прохождения анкеты 360 — открывается по клику «Заполнить»/«Продолжить»
 * с дашборда (StudentHome). Ответы сохраняются целиком одним запросом;
 * бэкенд upsert'ит и пересчитывает статус (submit_answers, Этап 4d).
 */
export function AssessmentFillPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const assessmentId = Number(id);

  const [detail, setDetail] = useState<AssessmentDetail | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAssessment(assessmentId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        const initial: Record<number, number> = {};
        for (const q of data.questions) {
          if (q.value !== null) initial[q.id] = q.value;
        }
        setAnswers(initial);
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

  if (!user) return null; // под RequireAuth недостижимо, но успокаивает типы

  const totalCount = detail?.questions.length ?? 0;
  const answeredCount = detail
    ? detail.questions.filter((q) => answers[q.id] !== undefined).length
    : 0;
  const percent = totalCount > 0 ? Math.round((answeredCount / totalCount) * 100) : 0;
  const allAnswered = totalCount > 0 && answeredCount === totalCount;

  const handleSelect = (questionId: number, value: number) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
    setJustSaved(false);
  };

  const handleSubmit = async () => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const payload = Object.entries(answers).map(([questionId, value]) => ({
        question_id: Number(questionId),
        value,
      }));
      const result = await submitAnswers(assessmentId, payload);
      if (result.status === 'completed') {
        navigate('/');
        return;
      }
      setJustSaved(true);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Не удалось сохранить ответы');
    } finally {
      setSubmitting(false);
    }
  };

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
      ) : detail ? (
        <>
          <h2>{detail.subject.full_name}</h2>
          <div className="assessment-fill__progress">
            <ProgressBar value={percent} className="assessment-fill__progress-bar" />
            <span>
              {answeredCount} из {totalCount} вопросов
            </span>
          </div>

          <Panel>
            {detail.questions.map((q) => (
              <div key={q.id} className="assessment-question">
                <div className="assessment-question__text">{q.text}</div>
                <div className="assessment-question__scale">
                  {SCALE.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={`assessment-question__option ${
                        answers[q.id] === value ? 'assessment-question__option--selected' : ''
                      }`.trim()}
                      onClick={() => handleSelect(q.id, value)}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </Panel>

          {submitError && <div className="form-error">{submitError}</div>}
          {justSaved && !submitError && (
            <div className="assessment-fill__saved">Ответы сохранены</div>
          )}

          <div className="assessment-fill__actions">
            <Button onClick={handleSubmit} disabled={submitting || answeredCount === 0}>
              {submitting ? 'Сохраняем…' : allAnswered ? 'Завершить' : 'Сохранить ответы'}
            </Button>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}
