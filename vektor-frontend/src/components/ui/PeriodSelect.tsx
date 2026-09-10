import type { CampaignRef } from '../../types/results';
import { formatPeriod } from '../../data/period';
import './PeriodSelect.css';

interface PeriodSelectProps {
  /** Периоды группы, свежие сверху (как их отдаёт бэкенд). */
  campaigns: CampaignRef[];
  /** undefined — «как решит бэкенд», см. defaultLabel. */
  value: number | undefined;
  onChange: (campaignId: number | undefined) => void;
  /**
   * Подпись варианта «без явного выбора». Он не косметический: без периода
   * профиль считается по НЫНЕШНЕМУ составу, беря у каждого ученика его
   * последнюю диагностику, — а это не то же самое, что «самый свежий период
   * из списка». Список к тому же шире: в нём есть архив прошлых наборов той
   * же строки класса.
   */
  defaultLabel?: string;
}

/**
 * Выбор периода диагностики на экранах группы.
 *
 * Один компонент на диагностику класса у учителя и аналитику класса у админа:
 * различий между ними нет вовсе, а разъехавшись, две копии по-разному
 * назвали бы вариант «по умолчанию» — самое неочевидное место этого выбора.
 *
 * Пустой список не рендерится: строка «Период» с единственным вариантом
 * читалась бы как сломанный фильтр.
 */
export function PeriodSelect({
  campaigns,
  value,
  onChange,
  defaultLabel = 'Последние диагностики этого состава',
}: PeriodSelectProps) {
  if (campaigns.length === 0) return null;

  const own = campaigns.filter((c) => c.is_current_cohort);
  const archive = campaigns.filter((c) => !c.is_current_cohort);
  const selected = value === undefined ? undefined : campaigns.find((c) => c.campaign_id === value);

  const options = (list: CampaignRef[]) =>
    list.map((campaign) => (
      <option key={campaign.campaign_id} value={campaign.campaign_id}>
        {optionLabel(campaign, campaigns)}
      </option>
    ));

  return (
    <div className="period-select">
      <div className="period-select__row">
        <span className="period-select__label">Период</span>
        <select
          className="period-select__control"
          value={value ?? ''}
          onChange={(event) =>
            onChange(event.target.value ? Number(event.target.value) : undefined)
          }
        >
          <option value="">{defaultLabel}</option>
          {/* Группы рисуем, только когда есть обе: заголовок над единственной
              группой ничего не разделяет, а место занимает. */}
          {own.length > 0 && archive.length > 0 ? (
            <>
              <optgroup label="Диагностика этого состава">{options(own)}</optgroup>
              <optgroup label="Архив класса — прежние наборы">{options(archive)}</optgroup>
            </>
          ) : (
            options(campaigns)
          )}
        </select>
      </div>

      {/* Оговорка про чужую когорту — под селектом, а не пометкой в самой
          опции: её нужно видеть ВСЁ время, пока открыт архив, иначе состав
          таблицы ниже читается как ошибка (школа переиспользует строки
          классов, и в прошлогодней диагностике 5-1 — сегодняшние шестые). */}
      {selected && !selected.is_current_cohort && (
        <div className="period-select__note">
          Прежний набор класса — сегодняшних учеников в этой диагностике нет
        </div>
      )}
    </div>
  );
}

/**
 * Подпись периода. Обычно достаточно «Июнь 2026»: название кампании
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
  // Идущая кампания помечается: у неё в таблице ниже будут незаполненные
  // анкеты, и это не пробел в данных, а нормальный ход диагностики.
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
