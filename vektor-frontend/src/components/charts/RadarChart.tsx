import { useState } from 'react';
import './RadarChart.css';

const SCALE_MIN = 1;
const SCALE_MAX = 5;
const RINGS = [2, 3, 4, 5];

/** Запас по бокам под подписи осей: они висят СНАРУЖИ круга и в квадратный
 *  viewBox не помещаются — крайние («Сильные стороны», «Проактивность»)
 *  обрезались краем svg. */
const PAD_X = 104;

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
  /** Полные названия критериев — в подсказку, где место есть. По умолчанию — `axes`. */
  axisTitles?: string[];
  series: RadarSeries[];
  size?: number;
}

interface HoveredAxis {
  index: number;
  x: number;
  y: number;
}

/**
 * Радар («паутинка») на голом SVG.
 *
 * В прототипе на этом месте Chart.js, но тянуть диаграммную библиотеку ради
 * одной фигуры дорого: здесь нужен многоугольник без анимаций и зума, а
 * единственное интерактивное место — подсказка по оси. Осей столько же, сколько критериев, — форма подстраивается
 * сама (11 критериев → 11-угольник, 5 → пятиугольник).
 */
export function RadarChart({ axes, axisTitles, series, size = 320 }: RadarChartProps) {
  const [hovered, setHovered] = useState<HoveredAxis | null>(null);

  const center = size / 2;
  // По вертикали подписи тоже снаружи, но там их всего одна-две и они короткие.
  const radius = size / 2 - 30;

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

  /**
   * Прозрачный сектор — зона наведения оси.
   *
   * Ловить сами вершины кружками неудобно: их по одной на серию, они
   * расходятся тем сильнее, чем больше разрыв, и попасть в тонкую точку
   * мышью трудно. Сектор ловит и вершины, и подпись, и всё между ними,
   * поэтому радиус берётся с запасом за подписи.
   */
  const wedgeFor = (index: number) => {
    const half = Math.PI / axes.length;
    const reach = radius + 46;
    const angle = angleFor(index);
    const a = { x: center + Math.cos(angle - half) * reach, y: center + Math.sin(angle - half) * reach };
    const b = { x: center + Math.cos(angle + half) * reach, y: center + Math.sin(angle + half) * reach };
    return `${center},${center} ${a.x.toFixed(1)},${a.y.toFixed(1)} ${b.x.toFixed(1)},${b.y.toFixed(1)}`;
  };

  return (
    <div className="radar">
      <svg
        viewBox={`${-PAD_X} 0 ${size + PAD_X * 2} ${size}`}
        className="radar__svg"
        role="img"
        onMouseLeave={() => setHovered(null)}
      >
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

        {/* Вершины наведённой оси — чтобы было видно, о каких точках речь. */}
        {hovered !== null &&
          series.map((item) => {
            const value = item.values[hovered.index];
            if (value === null || value === undefined) return null;
            const point = pointAt(hovered.index, value);
            return (
              <circle
                key={item.label}
                className="radar__dot"
                cx={point.x}
                cy={point.y}
                r={4}
                fill={item.color}
              />
            );
          })}

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
              className={`radar__label ${hovered?.index === index ? 'radar__label--active' : ''}`}
              x={x}
              y={y}
              textAnchor={anchor}
              dominantBaseline="middle"
            >
              {axis}
            </text>
          );
        })}

        {/* Зоны наведения — последними, поверх всего остального. */}
        {axes.map((axis, index) => {
          const track = (e: { clientX: number; clientY: number }) =>
            setHovered({ index, x: e.clientX, y: e.clientY });
          return (
            <polygon
              key={axis}
              className="radar__hit"
              points={wedgeFor(index)}
              onMouseEnter={track}
              onMouseMove={track}
            />
          );
        })}
      </svg>

      {hovered !== null && (
        <AxisTooltip
          title={(axisTitles ?? axes)[hovered.index]}
          series={series}
          index={hovered.index}
          x={hovered.x}
          y={hovered.y}
        />
      )}

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

/**
 * Значения одной оси у курсора — тем же приёмом, что раскрытие слоя в
 * покрытии кампании: position: fixed от координат курсора (подсказка обязана
 * вылезать за пределы svg), переворот у краёв окна, pointer-events: none,
 * чтобы курсор проходил насквозь и подсказка не мигала под собой.
 *
 * Лидирующая серия выделена, а разрыв подписан числом: на глаз по зазору
 * между контурами видно направление, но не величина.
 */
function AxisTooltip({
  title,
  series,
  index,
  x,
  y,
}: {
  title: string;
  series: RadarSeries[];
  index: number;
  x: number;
  y: number;
}) {
  const rows = series.map((item) => ({ item, value: item.values[index] ?? null }));
  const known = rows.filter((row) => row.value !== null);
  const best = known.length > 0 ? Math.max(...known.map((row) => row.value as number)) : null;
  // Подписываем разрыв только там, где он есть у ОБЕИХ сторон и заметен:
  // 0.5 балла — тот же порог, что был у подписей «себя выше на …».
  const gap =
    known.length === 2 ? Math.abs((known[0].value as number) - (known[1].value as number)) : null;
  const leader = known.find((row) => row.value === best);

  const width = 214;
  const height = 42 + rows.length * 22 + (gap !== null && gap >= 0.5 ? 20 : 0);
  const flipX = x + width + 24 > window.innerWidth;
  const flipY = y + height + 24 > window.innerHeight;

  return (
    <div
      className="radar-tip"
      style={{
        left: flipX ? x - width - 14 : x + 14,
        top: flipY ? Math.max(8, y - height - 14) : y + 14,
        width,
      }}
    >
      <div className="radar-tip__title">{title}</div>
      {rows.map((row) => (
        <div
          key={row.item.label}
          className={`radar-tip__row ${
            best !== null && row.value === best ? 'radar-tip__row--lead' : ''
          }`}
        >
          <span className="radar-tip__key" style={{ background: row.item.color }} />
          <span className="radar-tip__name">{row.item.label}</span>
          <span className="radar-tip__value">
            {row.value === null ? '—' : row.value.toFixed(1)}
          </span>
        </div>
      ))}
      {gap !== null && gap >= 0.5 && leader && (
        <div className="radar-tip__gap">
          {leader.item.label} выше на {gap.toFixed(1)}
        </div>
      )}
    </div>
  );
}
