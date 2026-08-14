import { useCallback } from 'react';
import { Panel } from '../ui/Panel';
import { CompetencyProfile } from './CompetencyProfile';
import { useApi } from '../../hooks/useApi';
import { fetchSubjectResults } from '../../api/results';

interface StudentResultsPanelProps {
  subjectId: number;
}

/**
 * Панель «Мои результаты».
 *
 * Отдельный компонент, а не кусок StudentHome: так хук загрузки вызывается
 * только когда subjectId уже известен, без non-null assertion на user внутри
 * зависимостей useCallback.
 */
export function StudentResultsPanel({ subjectId }: StudentResultsPanelProps) {
  // useApi требует стабильную ссылку — иначе effect уходит в цикл запросов.
  const load = useCallback(() => fetchSubjectResults(subjectId), [subjectId]);
  const results = useApi(load);

  // Критерии без итогового балла не рисуем: у восьмиклассника это блок
  // профпроб (он открывается с 9 класса), и строка с прочерками читалась бы
  // как «низкий результат», а не «ещё не измеряется».
  const scored = (results.data?.competencies ?? []).filter((c) => c.overall_avg !== null);

  return (
    <Panel title="Мои результаты">
      {results.loading ? (
        <div className="app-main__sub">Загрузка…</div>
      ) : results.error ? (
        /* 404 здесь — штатная ситуация «результатов ещё нет», а не сбой:
           у ученика может не быть ни одной кампании с анкетами. */
        <div className="app-main__sub">Результатов пока нет</div>
      ) : results.data ? (
        <>
          <div className="results-summary">
            <div className="results-summary__score">
              {results.data.overall_average === null
                ? '—'
                : results.data.overall_average.toFixed(2)}
            </div>
            <div className="results-summary__meta">
              средний балл по {scored.length} критериям
              <br />
              шкала 1–5
            </div>
          </div>

          {!results.data.any_peer_scores_disclosed && (
            /* Порог анонимности — 3 разных одноклассника ПО КАЖДОМУ критерию.
               Молчать про скрытый слой нельзя: иначе выглядит, будто
               одноклассники просто не отвечали. */
            <div className="app-main__sub results-note">
              Оценки одноклассников скрыты: их слишком мало, чтобы показать
              анонимно.
            </div>
          )}

          <CompetencyProfile competencies={scored} />

          {results.data.growth_zones.length > 0 && (
            <div className="results-zones">
              <div className="results-zones__title">Зоны роста</div>
              {results.data.growth_zones.map((zone) => (
                <div className="results-zones__item" key={zone.competency_id}>
                  <span>{zone.name}</span>
                  <span className="results-zones__score">{zone.overall_avg.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </Panel>
  );
}
