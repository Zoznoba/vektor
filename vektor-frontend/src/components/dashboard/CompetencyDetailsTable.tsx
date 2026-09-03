import './CompetencyDetailsTable.css';
import type { CompetencyScore } from '../../types/results';

const SCALE_MIN = 1;
const SCALE_MAX = 5;

// Секвенциальная шкала «один тон, светлее → темнее» на существующем синем
// акценте (--blue-tint → --blue-ink) — величина всегда про магнитуду балла,
// не про категорию, поэтому один hue, а не набор цветов.
const LIGHT_RGB = { r: 0xe9, g: 0xf2, b: 0xfe }; // --blue-tint
const DARK_RGB = { r: 0x1f, g: 0x66, b: 0xc4 }; // --blue-ink

function cellStyle(value: number | null): { background?: string; color?: string } {
  if (value === null) return {};
  const ratio = Math.min(1, Math.max(0, (value - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)));
  const r = Math.round(LIGHT_RGB.r + (DARK_RGB.r - LIGHT_RGB.r) * ratio);
  const g = Math.round(LIGHT_RGB.g + (DARK_RGB.g - LIGHT_RGB.g) * ratio);
  const b = Math.round(LIGHT_RGB.b + (DARK_RGB.b - LIGHT_RGB.b) * ratio);
  // Относительная светлота (упрощённо, по WCAG-подобной формуле) решает,
  // каким текстом читать ячейку — тёмным или белым.
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return {
    background: `rgb(${r}, ${g}, ${b})`,
    color: luminance > 0.6 ? 'var(--ink)' : '#ffffff',
  };
}

function Cell({ value }: { value: number | null }) {
  return (
    <td className="details-table__cell" style={cellStyle(value)}>
      {value === null ? <span className="details-table__dash">—</span> : value.toFixed(1)}
    </td>
  );
}

interface CompetencyDetailsTableProps {
  competencies: CompetencyScore[];
}

/**
 * Табличный вид тех же данных, что и радар выше по странице — для чтения
 * точных чисел по каждому слою разом, не только self/others (радар показывает
 * два контура, подсказка по оси — их же). Обязательный «табличный вид» результата поверх чарта:
 * heatmap-заливка тут дополняет число, а не заменяет его.
 */
export function CompetencyDetailsTable({ competencies }: CompetencyDetailsTableProps) {
  return (
    <div className="details-table-scroll">
      <table className="details-table">
        <thead>
          <tr>
            <th>Критерий</th>
            <th>Самооценка</th>
            <th>Однокл.</th>
            <th>Учителя</th>
            <th>Родители</th>
            <th>Итог</th>
          </tr>
        </thead>
        <tbody>
          {competencies.map((c) => (
            <tr key={c.competency_id}>
              <td className="details-table__name">{c.name}</td>
              <Cell value={c.self_avg} />
              <Cell value={c.peer_scores_disclosed ? c.peer_avg : null} />
              <Cell value={c.teacher_avg} />
              <Cell value={c.parent_avg} />
              <Cell value={c.overall_avg} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
