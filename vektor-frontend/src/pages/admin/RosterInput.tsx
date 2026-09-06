import type { RosterRow } from './roster';

/**
 * Поле вставки списка «ФИО ⇥ email» вместе с превью распознанных строк.
 *
 * Общий кусок двух мастеров массового заведения людей — «Новый класс» и
 * «Добавить пачкой» на «Пользователях». Разбор и валидация — снаружи
 * (`parseRoster`), сюда приходит уже готовый результат: компонент ничего не
 * решает, только показывает.
 */
export function RosterInput({
  value,
  onChange,
  rows,
  errorCount,
  placeholder,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  rows: RosterRow[];
  errorCount: number;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  return (
    <>
      <p className="roster-hint">
        Вставьте список — по одному человеку на строку в формате{' '}
        <strong>ФИО&nbsp;⇥&nbsp;email</strong> (можно скопировать два столбца прямо из Excel).
      </p>
      <textarea
        className="roster-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={7}
        placeholder={placeholder ?? 'Иванов Иван\tivanov.i@vektor.ru\nПетрова Анна\tpetrova.a@vektor.ru'}
        autoFocus={autoFocus}
      />

      {rows.length > 0 && (
        <>
          <div className="roster-summary">
            Распознано: {rows.length}{' '}
            {errorCount === 0 ? (
              <span className="roster-summary__ok">· ошибок нет ✓</span>
            ) : (
              <span className="roster-summary__err">· с ошибками: {errorCount}</span>
            )}
          </div>
          <div className="roster-preview">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Email</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={r.error ? 'roster-row--error' : ''}>
                    <td>{r.fullName || <span className="roster-cell--empty">—</span>}</td>
                    <td>{r.email || <span className="roster-cell--empty">—</span>}</td>
                    <td>
                      {r.error ? (
                        <span className="roster-status roster-status--err">{r.error}</span>
                      ) : (
                        <span className="roster-status roster-status--ok">✓</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
