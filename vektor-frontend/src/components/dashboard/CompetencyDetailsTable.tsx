import { useEffect, useMemo, useRef, useState } from 'react';
import './CompetencyDetailsTable.css';
import type { CompetencyScore } from '../../types/results';

const SCALE_MIN = 1;
const SCALE_MAX = 5;
const REVEAL_MS = 850; // держать в согласии с --reveal-dur в CSS

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
  // Строки таблицы keyed по позиции, а не по критерию: DOM-узел ячейки при
  // пересортировке остаётся на месте, меняется лишь inline-цвет → браузер сам
  // перетекает из прежнего цвета в новый (transition в CSS), без сброса.
  return (
    <td className="details-table__cell" style={cellStyle(value)}>
      {value === null ? <span className="details-table__dash">—</span> : value.toFixed(1)}
    </td>
  );
}

type SortKey = 'name' | 'self' | 'teacher' | 'parent' | 'overall';
type SortDir = 'asc' | 'desc';

const COLUMNS: { key: SortKey; label: string; value: (c: CompetencyScore) => number | string | null }[] = [
  { key: 'name', label: 'Критерий', value: (c) => c.name },
  { key: 'self', label: 'Самооценка', value: (c) => c.self_avg },
  { key: 'teacher', label: 'Учителя', value: (c) => c.teacher_avg },
  { key: 'parent', label: 'Родители', value: (c) => c.parent_avg },
  { key: 'overall', label: 'Итог', value: (c) => c.overall_avg },
];

function HeaderCell({
  column,
  sortKey,
  sortDir,
  onSort,
}: {
  column: (typeof COLUMNS)[number];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const active = sortKey === column.key;
  return (
    <th
      className={`details-table__th-sort ${active ? 'details-table__th-sort--active' : ''}`.trim()}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={() => onSort(column.key)}
    >
      {column.label}
      <span className="details-table__sort-caret">
        {active ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
      </span>
    </th>
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
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  // Перепечатка названий — только на смену сортировки, не на первой отрисовке.
  const [printToken, setPrintToken] = useState(0);
  const [printing, setPrinting] = useState(false);
  const firstRun = useRef(true);

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    setPrinting(true);
    setPrintToken((t) => t + 1);
    const timer = setTimeout(() => setPrinting(false), REVEAL_MS);
    return () => clearTimeout(timer);
  }, [sortKey, sortDir]);

  const onSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'name' ? 'asc' : 'desc');
    }
  };

  const sorted = useMemo(() => {
    const column = COLUMNS.find((c) => c.key === sortKey)!;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...competencies].sort((a, b) => {
      const av = column.value(a);
      const bv = column.value(b);
      if (typeof av === 'string' || typeof bv === 'string') {
        return dir * String(av).localeCompare(String(bv), 'ru');
      }
      // Пустые слои всегда снизу независимо от направления.
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return dir * (av - bv);
    });
  }, [competencies, sortKey, sortDir]);

  return (
    <div className="details-table-scroll">
      <table className={`details-table ${printing ? 'details-table--printing' : ''}`.trim()}>
        <thead>
          <tr>
            {COLUMNS.map((column) => (
              <HeaderCell
                key={column.key}
                column={column}
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={onSort}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((c, i) => (
            <tr key={i}>
              <td className="details-table__name">
                <span key={printToken} className="details-table__name-text">
                  {c.name}
                </span>
              </td>
              <Cell value={c.self_avg} />
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
