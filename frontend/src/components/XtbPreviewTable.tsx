import { useTranslation } from 'react-i18next'
import type { XtbPreviewRow } from '../api/portfoliosApi'
import { useTableSort } from '../hooks/useTableSort'
import { currencyLabel } from '../lib/format'
import { toPln } from '../lib/markets'
import { sortTableRows, type SortColumns } from '../lib/sorting'
import { SortHeader } from './ui'

type PreviewColumn = 'source' | 'date' | 'side' | 'instrument' | 'quantity' | 'price' | 'fees' | 'status'
const initialSortDir = (key: PreviewColumn) =>
  key === 'source' || key === 'side' || key === 'instrument' || key === 'status' ? 'asc' : 'desc'

export function XtbPreviewTable({ rows, message }: { rows: XtbPreviewRow[]; message: (code: string) => string }) {
  const { t, i18n } = useTranslation()
  const { sort, onHeaderSort } = useTableSort<PreviewColumn>(null, initialSortDir)
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 }).format
  const side = (row: XtbPreviewRow) => row.transaction ? t(`portfolio.${row.transaction.side}`) : null
  const status = (row: XtbPreviewRow) => row.code ? message(row.code) : t(`portfolio.xtb.${row.status}`)
  const currency = rows.find(row => row.transaction)?.transaction?.currency
  const compareInPln = rows.some(row => row.transaction && row.transaction.currency !== currency)
  const amount = (row: XtbPreviewRow, key: 'price' | 'fees') => {
    const trade = row.transaction
    if (!trade) return null
    const value = Number(trade[key])
    return compareInPln ? toPln(value, trade.currency) : value
  }
  const columns: SortColumns<XtbPreviewRow, PreviewColumn> = {
    source: row => `${row.sheet} · ${row.row}`,
    date: row => row.transaction ? Date.parse(row.transaction.executedAt ?? row.transaction.date) : null,
    side,
    instrument: row => row.transaction?.ticker ?? row.symbol,
    quantity: row => row.transaction ? Number(row.transaction.quantity) : null,
    price: row => amount(row, 'price'),
    fees: row => amount(row, 'fees'),
    status,
  }

  return <div className="max-h-80 overflow-auto rounded-md border border-slate-800">
    <table className="w-full whitespace-nowrap text-left text-xs">
      <thead className="text-slate-400"><tr>
        {(Object.keys(columns) as PreviewColumn[]).map(key => (
          <SortHeader key={key} col={key} sort={sort} onSort={onHeaderSort} compact
            label={t(key === 'source' || key === 'status' ? `portfolio.xtb.${key}` : `portfolio.${key}`)} />
        ))}
      </tr></thead>
      <tbody>{sortTableRows(rows, sort, columns, i18n.language).map(row => {
        const trade = row.transaction
        const formatAmount = (value: string) => `${number(Number(value))} ${currencyLabel(trade?.currency)}`
        return <tr key={`${row.sheet}:${row.row}`} className="border-t border-slate-800">
          <td className="p-2">{row.sheet} · {row.row}</td>
          <td className="p-2">{trade?.executedAt?.replace('T', ' ') ?? trade?.date ?? '-'}</td>
          <td className="p-2">{side(row) ?? '-'}</td>
          <td className="p-2">{trade?.ticker.toUpperCase() ?? row.symbol}</td>
          <td className="p-2">{trade ? number(Number(trade.quantity)) : '-'}</td>
          <td className="p-2">{trade ? formatAmount(trade.price) : '-'}</td>
          <td className="p-2">{trade ? formatAmount(trade.fees) : '-'}</td>
          <td className={'p-2 ' + (row.status === 'error' ? 'text-amber-400' : 'text-slate-300')}>{status(row)}</td>
        </tr>
      })}</tbody>
    </table>
  </div>
}
