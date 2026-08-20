import type { CompetencyClassScore } from '../../types/results';
import '../dashboard/CompetencyProfile.css';

const SCALE_MAX = 5;

interface ClassCompetencyProfileProps {
  competencies: CompetencyClassScore[];
}

function widthPercent(value: number): string {
  return `${(value / SCALE_MAX) * 100}%`;
}

/**
 * «Класс против школы» по критериям.
 *
 * В прототипе на этом месте радар, но диаграммной библиотеки в проекте нет, а
 * тянуть её ради одного экрана дорого. Полосы читаются тем же языком, что и
 * профиль ученика: верхняя — класс, нижняя — школа за тот же период.
 */
export function ClassCompetencyProfile({ competencies }: ClassCompetencyProfileProps) {
  return (
    <div className="competency-profile">
      <div className="competency-profile__legend">
        <span className="competency-profile__key competency-profile__key--self" />
        класс
        <span className="competency-profile__key competency-profile__key--others" />
        школа
      </div>

      {competencies.map((competency) => {
        const diff =
          competency.class_avg !== null && competency.school_avg !== null
            ? competency.class_avg - competency.school_avg
            : null;
        // Порог 0.3 балла: меньше — шум на трёх вопросах, подписывать нечего.
        const hint =
          diff !== null && Math.abs(diff) >= 0.3
            ? {
                label:
                  diff > 0
                    ? `выше школы на ${diff.toFixed(1)}`
                    : `ниже школы на ${Math.abs(diff).toFixed(1)}`,
                tone: diff > 0 ? 'sage' : 'amber',
              }
            : null;

        return (
          <div className="competency-row" key={competency.competency_id}>
            <div className="competency-row__head">
              <div className="competency-row__name">{competency.name}</div>
              <div className="competency-row__score">
                {competency.class_avg === null ? '—' : competency.class_avg.toFixed(2)}
              </div>
            </div>

            <div className="competency-row__bars">
              <div className="competency-row__track">
                {competency.class_avg !== null && (
                  <div
                    className="competency-row__bar competency-row__bar--self"
                    style={{ width: widthPercent(competency.class_avg) }}
                  />
                )}
              </div>
              <div className="competency-row__track">
                {competency.school_avg !== null && (
                  <div
                    className="competency-row__bar competency-row__bar--others"
                    style={{ width: widthPercent(competency.school_avg) }}
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
