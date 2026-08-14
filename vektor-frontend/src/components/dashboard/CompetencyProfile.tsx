import type { CompetencyScore } from '../../types/results';
import './CompetencyProfile.css';

const SCALE_MAX = 5;

interface CompetencyProfileProps {
  competencies: CompetencyScore[];
}

function widthPercent(value: number): string {
  return `${(value / SCALE_MAX) * 100}%`;
}

/**
 * Знак разрыва самооценки решает, что показывать пользователю:
 * себя выше окружающих — повод присмотреться, ниже — повод поддержать.
 * Порог 0.5 балла: меньше — статистический шум на трёх вопросах.
 */
function gapHint(gap: number | null): { label: string; tone: string } | null {
  if (gap === null || Math.abs(gap) < 0.5) return null;
  return gap > 0
    ? { label: `себя выше на ${gap.toFixed(1)}`, tone: 'amber' }
    : { label: `себя ниже на ${Math.abs(gap).toFixed(1)}`, tone: 'sage' };
}

/**
 * Профиль по 11 критериям методики.
 *
 * Показываем две полосы — самооценку и оценку окружающих: именно их
 * расхождение («разрыв самооценки») и есть содержательная часть 360°.
 * Итоговый балл вынесен цифрой справа, чтобы полосы читались как сравнение,
 * а не как три конкурирующих числа.
 */
export function CompetencyProfile({ competencies }: CompetencyProfileProps) {
  return (
    <div className="competency-profile">
      <div className="competency-profile__legend">
        <span className="competency-profile__key competency-profile__key--self" />
        самооценка
        <span className="competency-profile__key competency-profile__key--others" />
        окружающие
      </div>

      {competencies.map((competency) => {
        const hint = gapHint(competency.gap);
        return (
          <div className="competency-row" key={competency.competency_id}>
            <div className="competency-row__head">
              <span className="competency-row__name">{competency.name}</span>
              <span className="competency-row__score">
                {competency.overall_avg === null ? '—' : competency.overall_avg.toFixed(1)}
              </span>
            </div>

            <div className="competency-row__bars">
              <div className="competency-row__track">
                {competency.self_avg !== null && (
                  <div
                    className="competency-row__bar competency-row__bar--self"
                    style={{ width: widthPercent(competency.self_avg) }}
                  />
                )}
              </div>
              <div className="competency-row__track">
                {competency.others_avg !== null && (
                  <div
                    className="competency-row__bar competency-row__bar--others"
                    style={{ width: widthPercent(competency.others_avg) }}
                  />
                )}
              </div>
            </div>

            {hint && (
              <div className={`competency-row__hint competency-row__hint--${hint.tone}`}>
                {hint.label}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
