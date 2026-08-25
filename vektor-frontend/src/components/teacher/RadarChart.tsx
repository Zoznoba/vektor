import './RadarChart.css';

const SCALE_MIN = 1;
const SCALE_MAX = 5;
const RINGS = [2, 3, 4, 5];

export interface RadarSeries {
  label: string;
  /** Значения в шкале 1–5, по одному на ось; null — нет данных, точка на минимуме. */
  values: (number | null)[];
  /** CSS-цвет линии; заливка берётся с прозрачностью. */
  color: string;
  dashed?: boolean;
}

interface RadarChartProps {
  axes: string[];
  series: RadarSeries[];
  size?: number;
}

/**
 * Радар («паутинка») на голом SVG.
 *
 * В прототипе на этом месте Chart.js, но тянуть диаграммную библиотеку ради
 * одной фигуры дорого: здесь нужен статичный многоугольник без анимаций,
 * зума и тултипов. Осей столько же, сколько критериев, — форма подстраивается
 * сама (11 критериев → 11-угольник, 5 → пятиугольник).
 */
export function RadarChart({ axes, series, size = 320 }: RadarChartProps) {
  const center = size / 2;
  // Радиус с запасом под подписи осей по краям.
  const radius = size / 2 - 58;

  // Первая ось смотрит вверх: -90° — поворот от «трёх часов» к «двенадцати».
  const angleFor = (index: number) => (Math.PI * 2 * index) / axes.length - Math.PI / 2;

  const pointAt = (index: number, value: number) => {
    const ratio = (value - SCALE_MIN) / (SCALE_MAX - SCALE_MIN);
    const angle = angleFor(index);
    return {
      x: center + Math.cos(angle) * radius * ratio,
      y: center + Math.sin(angle) * radius * ratio,
    };
  };

  const polygonFor = (values: (number | null)[]) =>
    values
      .map((value, index) => {
        // null → точка на минимуме шкалы: разрыв контура читался бы как ноль,
        // а не как «нет данных», и фигура всё равно врала бы.
        const point = pointAt(index, value ?? SCALE_MIN);
        return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
      })
      .join(' ');

  return (
    <div className="radar">
      <svg viewBox={`0 0 ${size} ${size}`} className="radar__svg" role="img">
        {/* Кольца шкалы */}
        {RINGS.map((ring) => (
          <polygon
            key={ring}
            className="radar__ring"
            points={polygonFor(axes.map(() => ring))}
          />
        ))}

        {/* Лучи осей */}
        {axes.map((axis, index) => {
          const end = pointAt(index, SCALE_MAX);
          return (
            <line
              key={axis}
              className="radar__axis"
              x1={center}
              y1={center}
              x2={end.x}
              y2={end.y}
            />
          );
        })}

        {series.map((item) => (
          <polygon
            key={item.label}
            points={polygonFor(item.values)}
            fill={item.color}
            fillOpacity={0.1}
            stroke={item.color}
            strokeWidth={1.8}
            strokeDasharray={item.dashed ? '4 3' : undefined}
          />
        ))}

        {/* Подписи осей: якорь зависит от того, слева ось или справа, иначе
            крайние подписи наезжают на фигуру. */}
        {axes.map((axis, index) => {
          const angle = angleFor(index);
          const x = center + Math.cos(angle) * (radius + 14);
          const y = center + Math.sin(angle) * (radius + 14);
          const cos = Math.cos(angle);
          const anchor = cos > 0.2 ? 'start' : cos < -0.2 ? 'end' : 'middle';
          return (
            <text
              key={axis}
              className="radar__label"
              x={x}
              y={y}
              textAnchor={anchor}
              dominantBaseline="middle"
            >
              {axis}
            </text>
          );
        })}
      </svg>

      <div className="radar__legend">
        {series.map((item) => (
          <span className="radar__legend-item" key={item.label}>
            <span
              className="radar__legend-key"
              style={{
                background: item.dashed ? 'transparent' : item.color,
                borderTop: item.dashed ? `2px dashed ${item.color}` : undefined,
              }}
            />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
