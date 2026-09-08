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

type SortKey = 'name' | 'self' | 'others' | 'teacher' | 'parent' | 'overall';
type SortDir = 'asc' | 'desc';

interface Column {
  key: SortKey;
  label: string;
  value: (c: CompetencyScore) => number | string | null;
}

const NAME_COLUMN: Column = { key: 'name', label: 'Критерий', value: (c) => c.name };
const SELF_COLUMN: Column = { key: 'self', label: 'Самооценка', value: (c) => c.self_avg };
const OVERALL_COLUMN: Column = { key: 'overall', label: 'Итог', value: (c) => c.overall_avg };

/**
 * Набор колонок под режим панели — тот же, что у контуров радара выше.
 * `combined` — «окружающие» одним усреднённым слоем (единственное, что видит
 * ученик); `split` — учителя и родители по отдельности, для взрослых.
 */
const COLUMN_SETS: Record<'combined' | 'split', Column[]> = {
  combined: [
    NAME_COLUMN,
    SELF_COLUMN,
    { key: 'others', label: 'Окружающие', value: (c) => c.others_avg },
    OVERALL_COLUMN,
  ],
  split: [
    NAME_COLUMN,
    SELF_COLUMN,
    { key: 'teacher', label: 'Учителя', value: (c) => c.teacher_avg },
    { key: 'parent', label: 'Родители', value: (c) => c.parent_avg },
    OVERALL_COLUMN,
  ],
};

function HeaderCell({
  column,
  sortKey,
  sortDir,
  onSort,
}: {
  column: Column;
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
  /** Разбивка «окружающих» по ролям; ученику всегда `combined`. */
  layers?: 'combined' | 'split';
}

/**
 * Табличный вид тех же данных, что и радар выше по странице — для чтения
 * точных чисел. Состав колонок повторяет контуры радара (`layers`): ученик
 * видит только самооценку и «окружающих», взрослые — разбивку по ролям.
 * Обязательный «табличный вид» результата поверх чарта: heatmap-заливка тут
 * дополняет число, а не заменяет его.
 */
export function CompetencyDetailsTable({
  competencies,
  layers = 'split',
}: CompetencyDetailsTableProps) {
  const columns = COLUMN_SETS[layers];
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
    // Колонка сортировки могла исчезнуть вместе со сменой набора — тогда
    // падаем обратно на «Критерий», а не роняем таблицу на undefined.
    const column = columns.find((c) => c.key === sortKey) ?? NAME_COLUMN;
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
  }, [competencies, columns, sortKey, sortDir]);

  return (
    <div className="details-table-scroll">
      <table className={`details-table ${printing ? 'details-table--printing' : ''}`.trim()}>
        <thead>
          <tr>
            {columns.map((column) => (
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
              {columns.slice(1).map((column) => (
                <Cell key={column.key} value={column.value(c) as number | null} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
