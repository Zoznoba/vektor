import { useState } from 'react';
import './TrendChart.css';

export interface TrendPoint {
  /** Подпись под точкой — «Июнь 2026». */
  label: string;
  value: number;
  /** Вторая строка подсказки: «136 учеников». */
  note?: string;
  /** Точка, открытая на экране: обводится кольцом. */
  active?: boolean;
}

/**
 * Ряд по периодам — линия с точками, на голом SVG (тем же решением проекта не
 * тянуть Chart.js/recharts, что RadarChart и DynamicsChart).
 *
 * Серия ОДНА, поэтому легенды нет — её называет заголовок панели, а значение
 * каждой точки подписано прямо на графике: периодов единицы, и подпись у
 * каждого читается лучше, чем ось.
 *
 * Ось Y НЕ от нуля, в отличие от столбиков: у столбика длина и есть значение,
 * и обрезанная база врёт, а у линии значение — положение точки. Школьные
 * средние живут в диапазоне 3.0–3.5 балла из пяти, и на полной шкале
 * годовая разница была бы неотличима от прямой. Домен считается от данных с
 * запасом и подписан тиками, так что масштаб виден.
 */
export function TrendChart({ points }: { points: TrendPoint[] }) {
  const [hovered, setHovered] = useState<{ index: number; x: number; y: number } | null>(null);

  if (points.length === 0) return null;

  const width = 620;
  const height = 200;
  const marginLeft = 34;
  const marginRight = 16;
  const marginTop = 26;
  const marginBottom = 32;
  const plotWidth = width - marginLeft - marginRight;
  const plotHeight = height - marginTop - marginBottom;

  const values = points.map((p) => p.value);
  // Домен с запасом в половину балла и по границам шкалы 1–5: у одной точки
  // (первый год школы) min === max, и без запаса линия легла бы на край.
  const min = Math.max(1, Math.floor((Math.min(...values) - 0.5) * 2) / 2);
  const max = Math.min(5, Math.ceil((Math.max(...values) + 0.5) * 2) / 2);
  const span = max - min || 1;

  const xFor = (index: number) =>
    points.length === 1
      ? marginLeft + plotWidth / 2
      : marginLeft + (plotWidth * index) / (points.length - 1);
  const yFor = (value: number) => marginTop + plotHeight * (1 - (value - min) / span);

  const ticks = [min, min + span / 2, max];
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i)} ${yFor(p.value)}`).join(' ');

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} className="trend-chart__svg" role="img">
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              className="trend-chart__grid"
              x1={marginLeft}
              x2={width - marginRight}
              y1={yFor(tick)}
              y2={yFor(tick)}
            />
            <text
              className="trend-chart__tick"
              x={marginLeft - 8}
              y={yFor(tick)}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {tick.toFixed(1)}
            </text>
          </g>
        ))}

        {points.length > 1 && <path className="trend-chart__line" d={path} />}

        {points.map((point, index) => (
          <g key={point.label}>
            {point.active && (
              <circle
                className="trend-chart__halo"
                cx={xFor(index)}
                cy={yFor(point.value)}
                r={8}
              />
            )}
            <circle
              className="trend-chart__dot"
              cx={xFor(index)}
              cy={yFor(point.value)}
              r={4.5}
            />
            <text
              className="trend-chart__value"
              x={xFor(index)}
              y={yFor(point.value) - 12}
              textAnchor="middle"
            >
              {point.value.toFixed(2)}
            </text>
            <text
              className="trend-chart__label"
              x={xFor(index)}
              y={height - 10}
              textAnchor="middle"
            >
              {point.label}
            </text>
            {/* Зона наведения шире точки: попасть мышью в кружок радиусом
                4.5px трудно, а подсказка нужна ради числа учеников. */}
            <circle
              className="trend-chart__hit"
              cx={xFor(index)}
              cy={yFor(point.value)}
              r={16}
              onMouseEnter={(e) => setHovered({ index, x: e.clientX, y: e.clientY })}
              onMouseMove={(e) => setHovered({ index, x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHovered(null)}
            />
          </g>
        ))}
      </svg>

      {hovered !== null && (
        <div
          className="trend-tip"
          style={{
            left: hovered.x + 180 > window.innerWidth ? hovered.x - 194 : hovered.x + 14,
            top: hovered.y + 90 > window.innerHeight ? Math.max(8, hovered.y - 90) : hovered.y + 14,
          }}
        >
          <div className="trend-tip__title">{points[hovered.index].label}</div>
          <div className="trend-tip__value">{points[hovered.index].value.toFixed(2)}</div>
          {points[hovered.index].note && (
            <div className="trend-tip__note">{points[hovered.index].note}</div>
          )}
        </div>
      )}
    </div>
  );
}
