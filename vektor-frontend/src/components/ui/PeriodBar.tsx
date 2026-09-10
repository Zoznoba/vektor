import { useEffect, useId, useRef, useState } from 'react';
import type { CampaignRef } from '../../types/results';
import { formatPeriod } from '../../data/period';
import { Badge } from './Badge';
import { Icon } from '../icons/Icon';
import './PeriodBar.css';

interface PeriodBarProps {
  /** Что именно открыто: «Диагностика 8-1», «Класс 8-1». */
  title: string;
  /** Периоды группы, свежие сверху (как их отдаёт бэкенд). */
  campaigns: CampaignRef[];
  /**
   * Выбранный период. undefined бывает в двух случаях: список ещё грузится
   * или у нынешнего состава своей диагностики не было (см. defaultCampaignId).
   * Подставлять вместо этого архив прошлого набора нельзя — экран выглядел бы
   * рабочим и показывал чужих детей.
   */
  value: number | undefined;
  onChange: (campaignId: number) => void;
  loading?: boolean;
}

/**
 * Строка контекста экрана группы: «что мы смотрим» и «за какой период».
 *
 * Период здесь — не фильтр содержимого, а часть адреса того, что открыто: он
 * определяет, о каких вообще детях речь (школа переиспользует строки классов
 * из года в год, поэтому «8-1 в июне 2026» и «8-1 сегодня» — разные люди).
 * Отсюда и подача: отдельная полоса над контентом с названием группы, а не
 * подписанный `<select>` в ряду фильтров таблицы — та идиома обещает, что
 * ниже те же данные, только отобранные.
 *
 * Здесь же — то, что раньше жило порознь и читалось как не связанное друг с
 * другом: статус кампании (по идущей баллов ещё нет) и предупреждение про
 * прежний набор класса.
 */
export function PeriodBar({ title, campaigns, value, onChange, loading = false }: PeriodBarProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();

  // Тот же приём, что в ActionMenu: слушатели живут только пока меню открыто.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const selected = value === undefined ? undefined : campaigns.find((c) => c.campaign_id === value);
  const own = campaigns.filter((c) => c.is_current_cohort);
  const archive = campaigns.filter((c) => !c.is_current_cohort);
  const empty = !loading && campaigns.length === 0;

  return (
    <div className="period-bar" ref={rootRef}>
      <div className="period-bar__row">
        <span className="period-bar__title">{title}</span>
        <span className="period-bar__sep" aria-hidden="true">
          ·
        </span>

        <div className="period-bar__picker">
          <button
            type="button"
            className="period-bar__trigger"
            // Выбирать не из чего — кнопка мертва, но остаётся на месте:
            // пропав, она забрала бы с собой и объяснение, почему пусто.
            disabled={empty}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={open ? menuId : undefined}
            onClick={() => setOpen((prev) => !prev)}
          >
            {loading
              ? 'Загрузка…'
              : empty
                ? 'Диагностики не было'
                : selected
                  ? formatPeriod(selected.period_year, selected.period_month)
                  : 'Выберите период'}
            {!empty && <Icon name="chevronDown" size={14} />}
          </button>

          {open && (
            <div className="period-bar__menu" id={menuId} role="listbox">
              {/* Заголовки групп рисуем, только когда есть обе: над
                  единственной группой заголовок ничего не разделяет. */}
              {own.length > 0 && archive.length > 0 ? (
                <>
                  <Group label="Диагностика этого состава" campaigns={own}>
                    {renderOptions(own)}
                  </Group>
                  <Group label="Архив класса — прежние наборы" campaigns={archive}>
                    {renderOptions(archive)}
                  </Group>
                </>
              ) : (
                renderOptions(campaigns)
              )}
            </div>
          )}
        </div>

        {selected && (
          <span className="period-bar__status">
            {selected.status === 'closed' ? (
              <Badge variant="sage">Завершена</Badge>
            ) : (
              <Badge variant="amber">Идёт сейчас</Badge>
            )}
          </span>
        )}
      </div>

      {/* Оговорка про чужую когорту видна ВСЁ время, пока открыт архив: без
          неё состав ниже читается как ошибка. */}
      {selected && !selected.is_current_cohort && (
        <div className="period-bar__note">
          Прежний набор класса — сегодняшних учеников в этой диагностике нет
        </div>
      )}
    </div>
  );

  function renderOptions(list: CampaignRef[]) {
    return list.map((campaign) => {
      const active = campaign.campaign_id === value;
      return (
        <button
          key={campaign.campaign_id}
          type="button"
          role="option"
          aria-selected={active}
          className={`period-bar__option ${active ? 'period-bar__option--active' : ''}`.trim()}
          onClick={() => {
            setOpen(false);
            onChange(campaign.campaign_id);
          }}
        >
          <span className="period-bar__option-check">
            {active && <Icon name="check" size={14} />}
          </span>
          <span>{optionLabel(campaign, campaigns)}</span>
        </button>
      );
    });
  }
}

function Group({
  label,
  campaigns,
  children,
}: {
  label: string;
  campaigns: CampaignRef[];
  children: React.ReactNode;
}) {
  if (campaigns.length === 0) return null;
  return (
    <>
      <div className="period-bar__group">{label}</div>
      {children}
    </>
  );
}

/**
 * Подпись периода в списке. Обычно достаточно «Июнь 2026»: название кампании
 * («Диагностика 360 · 5-1 · 2026») повторяет и класс, и год, а различает
 * варианты как раз период.
 *
 * Название добавляем там, где период сам по себе неоднозначен — а это не
 * редкость: кампанию заводят на каждый класс отдельно, поэтому у класса,
 * собранного из двух прежних (10-й — из двух девятых), в одном июне лежит
 * несколько разных кампаний, и выбирать приходится именно между ними.
 */
function optionLabel(campaign: CampaignRef, all: CampaignRef[]): string {
  const samePeriod = all.filter(
    (c) => c.period_year === campaign.period_year && c.period_month === campaign.period_month,
  );
  const parts = [formatPeriod(campaign.period_year, campaign.period_month)];
  if (samePeriod.length > 1) parts.push(withoutYear(campaign.title));
  // Идущая кампания помечается и в списке: статус-бейдж виден только у уже
  // выбранной, а выбирать приходится до того.
  if (campaign.status !== 'closed') parts.push('идёт сейчас');
  return parts.join(' · ');
}

/**
 * Убирает год из названия кампании: он уже стоит в начале подписи, и
 * «Июнь 2026 · Диагностика 360 · 9-1 · 2026» читается как ошибка.
 *
 * Название — свободная строка, поэтому это чистая косметика: не нашёлся год —
 * возвращаем как есть, ничего не теряя.
 */
function withoutYear(title: string): string {
  return title.replace(/\s*·?\s*\b(19|20)\d{2}\b/, '').trim();
}
