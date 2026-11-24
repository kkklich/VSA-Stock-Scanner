import { Fragment, useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Play } from 'lucide-react'
import type { Instrument, PortfolioTotal, Position, Transaction } from '../api/portfoliosApi'
import { currencyLabel, deltaTone, fmtMoney, fmtPct } from '../lib/format'
import { canonicalTicker, toPln } from '../lib/markets'
import { useTableSort } from '../hooks/useTableSort'
import type { SortLevel } from '../lib/sorting'
import { SortHeader } from './ui'

const filterInput = 'rounded-md border border-slate-700 bg-slate-950 px-2.5 py-2 text-sm'
const control = 'rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40'
const table = 'w-full whitespace-nowrap text-left text-sm'
const cell = 'px-4 py-3'

type SortColumn<Row> =
  | { value: (row: Row) => number | string | null; monetary?: 'currency' }
  | { value: (row: Row) => number | null; monetary: 'pln' }

function sortRows<Row extends { currency: string }, Key extends string>(
  rows: Row[], sort: SortLevel<Key>[], columns: Record<Key, SortColumn<Row>>, locale: string,
) {
  if (!sort.length) return rows
  const { compare } = new Intl.Collator(locale, { numeric: true, sensitivity: 'base' })
  return rows.sort((a, b) => {
    for (const { key, dir } of sort) {
      const column = columns[key]
      const left = column.monetary === 'pln' ? toPln(column.value(a), a.currency) : column.value(a)
      const right = column.monetary === 'pln' ? toPln(column.value(b), b.currency) : column.value(b)
      if (left === null || right === null) {
        if (left !== right) return left === null ? 1 : -1
        continue
      }
      if (column.monetary === 'currency') {
        const byCurrency = compare(currencyLabel(a.currency), currencyLabel(b.currency))
        if (byCurrency) return byCurrency
      }
      const order = typeof left === 'number' && typeof right === 'number'
        ? left - right : compare(String(left), String(right))
      if (order) return dir === 'asc' ? order : -order
    }
    return 0
  })
}

function hasMultipleCurrencies(rows: { currency: string }[]) {
  return rows.some(row => currencyLabel(row.currency) !== currencyLabel(rows[0].currency))
}

function money(amount: number | null, currency: string) {
  return amount === null ? '—' : fmtMoney(amount, currency)
}

function pnl(amount: number | null, percent: number | null, currency: string) {
  return `${money(amount, currency)}${percent === null ? '' : ` (${fmtPct(percent)})`}`
}

function CurrencyFilter({ rows, value, onChange }: {
  rows: { currency: string }[]; value: string; onChange: (currency: string) => void
}) {
  const { t } = useTranslation()
  const currencies = [...new Set(rows.map(row => currencyLabel(row.currency)))].sort()
  if (value && !currencies.includes(value)) currencies.push(value)
  return <label className="grid gap-1 text-xs text-slate-400">
    {t('portfolio.filters.currency')}
    <select className={filterInput} value={value} onChange={event => onChange(event.target.value)}>
      <option value="">{t('portfolio.filters.all')}</option>
      {currencies.map(currency => <option key={currency}>{currency}</option>)}
    </select>
  </label>
}

export function PortfolioTotals({ totals }: { totals: PortfolioTotal[] }) {
  const { t } = useTranslation()
  return <div className="grid gap-3 lg:grid-cols-2">{totals.map(total => <section key={total.currency} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
    <h3 className="mb-3 font-semibold">{currencyLabel(total.currency)}</h3>
    <dl className="grid grid-cols-2 gap-3 text-sm">
      <div><dt className="text-slate-400">{t('portfolio.marketValue')}</dt><dd className="text-xl font-semibold">{money(total.marketValue, total.currency)}</dd></div>
      <div><dt className="text-slate-400">{t('portfolio.cost')}</dt><dd>{money(total.marketValue === null ? null : total.cost, total.currency)}</dd></div>
      <div><dt className="text-slate-400">{t('portfolio.unrealized')}</dt><dd className={deltaTone(total.unrealizedPnl ?? 0)}>{pnl(total.unrealizedPnl, total.unrealizedPnlPct, total.currency)}</dd></div>
      <div><dt className="text-slate-400">{t('portfolio.realized')}</dt><dd>{money(total.realizedPnl, total.currency)}</dd></div>
    </dl>
    {!!total.missingQuotes && <p className="mt-3 text-sm text-amber-400">{t('portfolio.missingQuotes', { count: total.missingQuotes })}</p>}
  </section>)}</div>
}

function positionStatus(position: Position) {
  return position.quantity > 0 ? 'active' : 'closed'
}

type PositionColumn = 'instrument' | 'positionStatus' | 'quantity' | 'averagePrice' | 'currentPrice'
  | 'marketValue' | 'unrealized' | 'unrealizedPct' | 'realized' | 'quoteDate'

const positionColumns: Record<PositionColumn, SortColumn<Position>> = {
  instrument: { value: position => position.ticker },
  positionStatus: { value: positionStatus },
  quantity: { value: position => position.quantity },
  averagePrice: { value: position => position.averagePrice, monetary: 'pln' },
  currentPrice: { value: position => position.currentPrice, monetary: 'pln' },
  marketValue: { value: position => position.marketValue, monetary: 'pln' },
  unrealized: { value: position => position.unrealizedPnl, monetary: 'pln' },
  unrealizedPct: { value: position => position.unrealizedPnlPct },
  realized: { value: position => position.realizedPnl, monetary: 'pln' },
  quoteDate: { value: position => position.quoteDate },
}

type TransactionRow = Transaction & { sourceWallet?: { id: string; label: string } }

function positionKey({ ticker, currency }: Pick<Position, 'ticker' | 'currency'>) {
  return `${ticker}:${currency}`
}

function PositionTransactions({ trades, label }: { trades: TransactionRow[]; label: string }) {
  const { t, i18n } = useTranslation()
  const { sort, onHeaderSort } = useTableSort<TransactionColumn>({ key: 'date', dir: 'desc' }, transactionSortDir)
  if (!trades.length) return <p className="text-slate-400">{t('portfolio.emptyTransactions')}</p>

  const showWallet = trades.some(trade => trade.sourceWallet)
  const keys = transactionColumnKeys.filter(key => key !== 'instrument' && (showWallet || key !== 'sourceWallet'))
  const rows = sortRows([...trades].reverse(), sort, transactionColumns, i18n.language)

  return <table className="whitespace-nowrap text-left text-sm" aria-label={label}>
    <thead className="text-xs text-slate-400"><tr>
      {keys.map(key => <SortHeader key={key} label={t('portfolio.' + key)} col={key} sort={sort} onSort={onHeaderSort} compact />)}
    </tr></thead>
    <tbody>{rows.map(trade => <tr key={trade.sourceWallet ? `${trade.sourceWallet.id}:${trade.id}` : trade.id} className="border-t border-slate-800">
      <td className={cell}><time dateTime={trade.date}>{trade.date}</time></td>
      <td className={cell}>{t(`portfolio.${trade.side}`)}</td>
      <td className={cell}>{Number(trade.quantity).toLocaleString(i18n.language, { maximumFractionDigits: 8 })}</td>
      <td className={cell}>
        {Number(trade.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })} {currencyLabel(trade.currency)}
      </td>
      <td className={cell}>{fmtMoney(Number(trade.fees), trade.currency)}</td>
      {showWallet && <td className={cell}>{trade.sourceWallet?.label}</td>}
    </tr>)}</tbody>
  </table>
}

const positionColumnKeys = Object.keys(positionColumns) as PositionColumn[]
const positionSortDir = (key: PositionColumn) => key === 'instrument' || key === 'positionStatus' ? 'asc' : 'desc'

export function PortfolioPositions({ positions, instruments, transactions }: {
  positions: Position[]; instruments: Instrument[]; transactions: TransactionRow[]
}) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const instrumentNames = useMemo(() => new Map(instruments.map(instrument =>
    [canonicalTicker(instrument.ticker).toLowerCase(), instrument.name],
  )), [instruments])
  const tradesByPosition = useMemo(() => {
    const grouped = new Map<string, TransactionRow[]>()
    for (const trade of transactions) {
      const key = positionKey(trade)
      const trades = grouped.get(key)
      if (trades) trades.push(trade)
      else grouped.set(key, [trade])
    }
    return grouped
  }, [transactions])
  const [expandedPositions, setExpandedPositions] = useState<Set<string>>(() => new Set())
  const [ticker, setTicker] = useState('')
  const [status, setStatus] = useState('active')
  const [currency, setCurrency] = useState('')
  const { sort, onHeaderSort } = useTableSort<PositionColumn>(null, positionSortDir)
  const query = ticker.trim().toLowerCase()
  const rows = sortRows(positions.filter(position =>
    (position.ticker.toLowerCase().includes(query)
      || !!instrumentNames.get(canonicalTicker(position.ticker).toLowerCase())?.toLowerCase().includes(query))
    && (!status || status === positionStatus(position))
    && (!currency || currency === currencyLabel(position.currency)),
  ), sort, positionColumns, i18n.language)

  return <section aria-labelledby={id}>
    <h3 id={id} className="mb-3 font-semibold">{t('portfolio.holdings')}</h3>
    {positions.length > 0 ? <>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="grid gap-1 text-xs text-slate-400">{t('portfolio.filters.tickerOrName')}
          <input className={filterInput} type="search" value={ticker} onChange={event => setTicker(event.target.value)} />
        </label>
        <label className="grid gap-1 text-xs text-slate-400">{t('portfolio.positionStatus')}
          <select className={filterInput} value={status} onChange={event => setStatus(event.target.value)}>
            <option value="">{t('portfolio.filters.all')}</option>
            <option value="active">{t('portfolio.active')}</option>
            <option value="closed">{t('portfolio.closed')}</option>
          </select>
        </label>
        <CurrencyFilter rows={positions} value={currency} onChange={setCurrency} />
        {(ticker || status || currency) && <button type="button" className={control} onClick={() => {
          setTicker(''); setStatus(''); setCurrency('')
        }}>{t('portfolio.filters.clear')}</button>}
      </div>
      {sort.some(({ key }) => positionColumns[key].monetary === 'pln') && hasMultipleCurrencies(rows) && <p className="mb-2 text-xs text-slate-400">
        {t('portfolio.filters.plnSort')}
      </p>}
      <div className="overflow-x-auto">
        <table className={table} aria-labelledby={id}>
          <thead className="text-xs text-slate-400"><tr>
            <th scope="col"><span className="sr-only">{t('portfolio.transactions')}</span></th>
            {positionColumnKeys.map(key => (
              <SortHeader key={key} label={t(`portfolio.${key}`)} col={key} sort={sort}
                onSort={onHeaderSort} />
            ))}
          </tr></thead>
          <tbody>{rows.map(position => {
            const key = positionKey(position)
            const expanded = expandedPositions.has(key)
            const detailsId = `${id}-trades-${encodeURIComponent(key)}`
            const label = t('portfolio.positionTransactions', {
              ticker: position.ticker.toUpperCase(), currency: currencyLabel(position.currency),
            })
            const rowStatus = positionStatus(position)
            const name = instrumentNames.get(canonicalTicker(position.ticker).toLowerCase())
            return <Fragment key={key}>
              <tr className="border-t border-slate-800">
                <td className="pl-2">
                  <button type="button" aria-label={label} aria-expanded={expanded} aria-controls={detailsId}
                    className="grid size-8 place-items-center rounded text-slate-400 hover:bg-slate-800 hover:text-slate-100 focus-visible:outline-2 focus-visible:outline-emerald-500"
                    onClick={() => setExpandedPositions(current => {
                      const next = new Set(current)
                      if (next.has(key)) next.delete(key)
                      else next.add(key)
                      return next
                    })}>
                    <Play aria-hidden="true" size={11} fill="currentColor"
                      className={`motion-safe:transition-transform ${expanded ? 'rotate-90' : ''}`} />
                  </button>
                </td>
                <td className={cell}>
                  <Link className="text-emerald-400 hover:underline" to={`/stock/${encodeURIComponent(position.ticker)}`}>
                    {position.ticker.toUpperCase()}
                  </Link>
                  {name && <span className="mt-0.5 block max-w-48 whitespace-normal text-xs text-slate-400">{name}</span>}
                </td>
                <td className={cell}><span className={`rounded-full px-2 py-1 text-xs font-medium ${rowStatus === 'active'
                  ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-800 text-slate-300'}`}>
                  {t(`portfolio.${rowStatus}`)}
                </span></td>
                <td className={cell}>{Number(position.quantity).toLocaleString(i18n.language, { maximumFractionDigits: 8 })}</td>
                <td className={cell}>{money(position.averagePrice, position.currency)}</td>
                <td className={cell}>{money(position.currentPrice, position.currency)}</td>
                <td className={cell}>{money(position.marketValue, position.currency)}</td>
                <td className={`${cell} ${deltaTone(position.unrealizedPnl ?? 0)}`}>
                  {money(position.unrealizedPnl, position.currency)}
                </td>
                <td className={`${cell} ${deltaTone(position.unrealizedPnlPct ?? 0)}`}>
                  {position.unrealizedPnlPct === null ? '-' : fmtPct(position.unrealizedPnlPct)}
                </td>
                <td className={cell}>{money(position.realizedPnl, position.currency)}</td>
                <td className={cell}>
                  {position.quoteDate ?? t('portfolio.noQuote')}
                  {position.quoteAsOf && <span className="block text-xs text-slate-400">{new Date(position.quoteAsOf).toLocaleTimeString(i18n.language)}</span>}
                  {position.quoteSource && <span className="block text-xs text-slate-400">{t(`portfolio.quote_${position.quoteSource}`)}</span>}
                  {rowStatus === 'active' && position.quoteAgeDays !== null && position.quoteAgeDays > 7 && <span className="block text-xs text-amber-400">
                    {t('portfolio.oldQuote', { count: position.quoteAgeDays })}
                  </span>}
                </td>
              </tr>
              <tr id={detailsId} hidden={!expanded} className="border-t border-slate-800 bg-slate-900/50">
                <td colSpan={positionColumnKeys.length + 1} className="px-4 py-2">
                  {expanded && <PositionTransactions trades={tradesByPosition.get(key) ?? []} label={label} />}
                </td>
              </tr>
            </Fragment>
          })}</tbody>
        </table>
      </div>
      {!rows.length && <p role="status" className="mt-3 text-sm text-slate-400">{t('portfolio.filters.noPositions')}</p>}
    </> : <p className="text-sm text-slate-400">{t('portfolio.emptyHoldings')}</p>}
  </section>
}

type TransactionColumn = 'date' | 'side' | 'instrument' | 'quantity' | 'price' | 'fees' | 'sourceWallet'

const transactionColumns: Record<TransactionColumn, SortColumn<TransactionRow>> = {
  date: { value: trade => trade.date },
  side: { value: trade => trade.side },
  instrument: { value: trade => trade.ticker },
  quantity: { value: trade => Number(trade.quantity) },
  price: { value: trade => Number(trade.price), monetary: 'currency' },
  fees: { value: trade => Number(trade.fees), monetary: 'currency' },
  sourceWallet: { value: trade => trade.sourceWallet?.label ?? null },
}
const transactionColumnKeys = Object.keys(transactionColumns) as TransactionColumn[]
const transactionSortDir = (key: TransactionColumn) => key === 'side' || key === 'instrument' || key === 'sourceWallet' ? 'asc' : 'desc'

export function PortfolioTransactionHistory({ transactions, busy, onRemove }: {
  transactions: TransactionRow[]; busy?: boolean; onRemove?: (trade: Transaction) => void
}) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const [expanded, setExpanded] = useState(false)
  const [ticker, setTicker] = useState('')
  const [side, setSide] = useState('')
  const [currency, setCurrency] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const { sort, onHeaderSort } = useTableSort<TransactionColumn>({ key: 'date', dir: 'desc' }, transactionSortDir)
  const query = ticker.trim().toLowerCase()
  const invalidDates = from !== '' && to !== '' && from > to
  const showWallet = expanded && transactions.some(trade => trade.sourceWallet)
  const visibleSort = sort.filter(({ key }) => showWallet || key !== 'sourceWallet')
  // A stable sort keeps the most recently recorded trade first on ties.
  const rows = expanded ? sortRows(transactions.filter(trade =>
    trade.ticker.toLowerCase().includes(query)
    && (!side || side === trade.side)
    && (!currency || currency === currencyLabel(trade.currency))
    && (!from || trade.date >= from)
    && (!to || trade.date <= to),
  ).reverse(), visibleSort, transactionColumns, i18n.language) : []

  return <section aria-labelledby={id}>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h3 id={id} className="font-semibold">{t('portfolio.transactions')}</h3>
      <button type="button" className={control} aria-expanded={expanded} aria-controls={`${id}-history`}
        onClick={() => setExpanded(open => !open)}>
        {t(expanded ? 'portfolio.hideHistory' : 'portfolio.showHistory')}
      </button>
    </div>
    <div id={`${id}-history`} hidden={!expanded}>
      {expanded && (transactions.length > 0 ? <>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label className="grid gap-1 text-xs text-slate-400">{t('portfolio.filters.ticker')}
            <input className={filterInput} type="search" value={ticker} onChange={event => setTicker(event.target.value)} />
          </label>
          <label className="grid gap-1 text-xs text-slate-400">{t('portfolio.filters.side')}
            <select className={filterInput} value={side} onChange={event => setSide(event.target.value)}>
              <option value="">{t('portfolio.filters.all')}</option>
              <option value="buy">{t('portfolio.buy')}</option>
              <option value="sell">{t('portfolio.sell')}</option>
            </select>
          </label>
          <CurrencyFilter rows={transactions} value={currency} onChange={setCurrency} />
          <label className="grid gap-1 text-xs text-slate-400">{t('portfolio.filters.from')}
            <input className={filterInput} type="date" value={from} onChange={event => setFrom(event.target.value)} />
          </label>
          <label className="grid gap-1 text-xs text-slate-400">{t('portfolio.filters.to')}
            <input className={filterInput} type="date" value={to} onChange={event => setTo(event.target.value)} />
          </label>
          {(ticker || side || currency || from || to) && <button type="button" className={control} onClick={() => {
            setTicker(''); setSide(''); setCurrency(''); setFrom(''); setTo('')
          }}>{t('portfolio.filters.clear')}</button>}
        </div>
        {visibleSort.some(({ key }) => transactionColumns[key].monetary) && hasMultipleCurrencies(rows) && <p className="mb-2 text-xs text-slate-400">
          {t('portfolio.filters.currencySort')}
        </p>}
        <div className="overflow-x-auto">
          <table className={table} aria-labelledby={id}>
            <thead className="text-xs text-slate-400"><tr>
              {transactionColumnKeys.filter(key => showWallet || key !== 'sourceWallet').map(key => (
                <SortHeader key={key} label={t('portfolio.' + key)} col={key} sort={visibleSort} onSort={onHeaderSort} />
              ))}
              {onRemove && <th scope="col" className={`${cell} font-medium`}>{t('portfolio.actions')}</th>}
            </tr></thead>
            <tbody>{rows.map(trade => <tr key={trade.sourceWallet ? `${trade.sourceWallet.id}:${trade.id}` : trade.id} className="border-t border-slate-800">
              <td className={cell}>{trade.date}</td>
              <td className={cell}>{t(`portfolio.${trade.side}`)}</td>
              <td className={cell}>{trade.ticker.toUpperCase()}</td>
              <td className={cell}>{Number(trade.quantity).toLocaleString(i18n.language, { maximumFractionDigits: 8 })}</td>
              <td className={cell}>{fmtMoney(Number(trade.price), trade.currency)}</td>
              <td className={cell}>{fmtMoney(Number(trade.fees), trade.currency)}</td>
              {showWallet && <td className={cell}>{trade.sourceWallet?.label}</td>}
              {onRemove && <td className={cell}><button type="button" className={control} disabled={busy} onClick={() => onRemove(trade)}>{t('portfolio.delete')}</button></td>}
            </tr>)}</tbody>
          </table>
        </div>
        {!rows.length && <p role="status" className="mt-3 text-sm text-slate-400">
          {t(invalidDates ? 'portfolio.filters.invalidDates' : 'portfolio.filters.noTransactions')}
        </p>}
      </> : <p className="text-sm text-slate-400">{t('portfolio.emptyTransactions')}</p>)}
    </div>
  </section>
}
