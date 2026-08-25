import './DynamicsChart.css';
import type { CompetencyDynamics } from '../../types/results';
import { shortCompetencyName } from '../../data/competencyShortNames';

const SCALE_MIN = 0;
const SCALE_MAX = 5;

interface DynamicsChartProps {
  competencies: CompetencyDynamics[];
  previousLabel: string;
  currentLabel: string;
}

/**
 * Групповой bar-чарт «пред. период vs текущий» по критериям, на голом SVG —
 * тем же приёмом, что и RadarChart (без диаграммных библиотек).
 *
 * Критерий без previous_avg (in_core === false) рисуется одним столбиком:
 * это не ноль, а «критерий появился в этом периоде» — либо возрастной блок
 * открылся (профпробы с 9 класса), либо состав анкеты изменился между годами.
 */
export function DynamicsChart({ competencies, previousLabel, currentLabel }: DynamicsChartProps) {
  const width = 640;
  const height = 260;
  const marginLeft = 28;
  const marginBottom = 62;
  const marginTop = 10;
  const plotWidth = width - marginLeft - 10;
  const plotHeight = height - marginTop - marginBottom;

  const groupWidth = plotWidth / competencies.length;
  const barWidth = Math.min(20, groupWidth / 2 - 4);

  const yFor = (value: number) =>
    marginTop + plotHeight * (1 - (value - SCALE_MIN) / (SCALE_MAX - SCALE_MIN));

  const gridValues = [0, 1, 2, 3, 4, 5];

  return (
    <div className="dynamics-chart">
      <svg viewBox={`0 0 ${width} ${height}`} className="dynamics-chart__svg" role="img">
        {gridValues.map((v) => (
          <line
            key={v}
            className="dynamics-chart__grid"
            x1={marginLeft}
            x2={width - 10}
            y1={yFor(v)}
            y2={yFor(v)}
          />
        ))}
        {gridValues.map((v) => (
          <text key={v} className="dynamics-chart__tick" x={marginLeft - 6} y={yFor(v)} textAnchor="end" dominantBaseline="middle">
            {v}
          </text>
        ))}

        {competencies.map((c, index) => {
          const groupX = marginLeft + index * groupWidth;
          const center = groupX + groupWidth / 2;
          const hasPrevious = c.previous_avg !== null;

          const currentX = hasPrevious ? center + 2 : center - barWidth / 2;
          const previousX = center - barWidth - 2;

          return (
            <g key={c.competency_id}>
              {hasPrevious && (
                <rect
                  className="dynamics-chart__bar dynamics-chart__bar--previous"
                  x={previousX}
                  y={yFor(c.previous_avg as number)}
                  width={barWidth}
                  height={yFor(SCALE_MIN) - yFor(c.previous_avg as number)}
                  rx={2}
                />
              )}
              {c.overall_avg !== null && (
                <rect
                  className="dynamics-chart__bar dynamics-chart__bar--current"
                  x={currentX}
                  y={yFor(c.overall_avg)}
                  width={barWidth}
                  height={yFor(SCALE_MIN) - yFor(c.overall_avg)}
                  rx={2}
                >
                  {!hasPrevious && <title>Критерий появился в этом периоде — сравнить не с чем</title>}
                </rect>
              )}
              <text
                className="dynamics-chart__label"
                x={center}
                y={yFor(SCALE_MIN) + 8}
                textAnchor="end"
                transform={`rotate(-40 ${center} ${yFor(SCALE_MIN) + 8})`}
              >
                {shortCompetencyName(c.code, c.name)}
                {!hasPrevious && ' *'}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="dynamics-chart__legend">
        <span className="dynamics-chart__legend-item">
          <span className="dynamics-chart__legend-key dynamics-chart__legend-key--previous" />
          {previousLabel}
        </span>
        <span className="dynamics-chart__legend-item">
          <span className="dynamics-chart__legend-key dynamics-chart__legend-key--current" />
          {currentLabel}
        </span>
        {competencies.some((c) => c.previous_avg === null) && (
          <span className="dynamics-chart__legend-item">* — нет данных за прошлый период</span>
        )}
      </div>
    </div>
  );
}
