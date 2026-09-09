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
   * Подпись варианта «без явного выбора». Он не косметический: по умолчанию
   * бэкенд открывает последнюю кампанию НЫНЕШНЕЙ когорты, и это другое
   * поведение, чем «самый свежий период из списка» — список шире, в нём есть
   * архив прошлых наборов той же строки класса.
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
  defaultLabel = 'Последняя у нынешнего состава',
}: PeriodSelectProps) {
  if (campaigns.length === 0) return null;

  return (
    <div className="period-select">
      <span className="period-select__label">Период</span>
      <select
        className="period-select__control"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : undefined)}
      >
        <option value="">{defaultLabel}</option>
        {campaigns.map((campaign) => (
          <option key={campaign.campaign_id} value={campaign.campaign_id}>
            {campaign.title} · {formatPeriod(campaign.period_year, campaign.period_month)}
          </option>
        ))}
      </select>
    </div>
  );
}
