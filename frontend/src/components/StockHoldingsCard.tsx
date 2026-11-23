import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { StockHoldings, StockWalletHolding } from '../api/portfoliosApi'
import type { ApiStockSignals } from '../api/stocksApi'
import { currencyLabel, deltaTone, fmtMoney, fmtPct, majorCurrency } from '../lib/format'
import { CollapsibleCard, SortHeader } from './ui'
import { useTableSort } from '../hooks/useTableSort'
import { sortTableRows, type SortColumns } from '../lib/sorting'
import { toPln } from '../lib/markets'

interface StockHoldingsProps {
  holdings: StockHoldings | 'error' | null
  quote?: Pick<ApiStockSignals, 'lastPrice' | 'currency'> | null
  onRetry: () => void
}

function inMajorUnits(amount: number, currency: string) {
  return currencyLabel(currency) === 'GBX' ? amount / 100 : amount
}

interface StockPrice {
  currency: string
  unitValue: number | null
}

function openPnl(quantity: number | null, cost: number | null, currency: string, price: StockPrice) {
  if (quantity === null || cost === null) return null
  if (!quantity) return 0
  if (price.unitValue === null || majorCurrency(currency) !== price.currency) return null
  return quantity * price.unitValue - inMajorUnits(cost, currency)
}

function PnlAmount({ amount, currency, cost }: { amount: number | null; currency: string; cost?: number | null }) {
  if (amount === null) return <>—</>
  // Match the precision of the displayed amount when assigning its colour and sign.
  const rounded = Math.abs(amount) < 0.005 ? 0 : amount
  return <span className={deltaTone(rounded)}>
    {rounded > 0 ? '+' : ''}{fmtMoney(rounded, currency)}
    {cost ? ` (${fmtPct(amount / cost * 100)})` : ''}
  </span>
}

function PnlSummary({ positions, price }: { positions: StockWalletHolding['positions']; price: StockPrice }) {
  const { t } = useTranslation()
  const totals = new Map<string, { realized: number; unrealized: number | null; cost: number }>()
  for (const { currency, quantity, cost, realizedPnl } of positions) {
    const key = majorCurrency(currency)
    const total = totals.get(key) ?? { realized: 0, unrealized: 0, cost: 0 }
    const unrealized = openPnl(quantity, cost, currency, price)
    total.realized += inMajorUnits(realizedPnl, currency)
    total.unrealized = total.unrealized === null || unrealized === null ? null : total.unrealized + unrealized
    total.cost += inMajorUnits(cost, currency)
    totals.set(key, total)
  }

  return <dl className="flex flex-wrap gap-x-5 gap-y-2 text-xs tabular-nums">
    {(['realized', 'unrealized', 'total'] as const).map(kind => (
      <div key={kind}>
        <dt className="text-slate-400">{t(kind === 'total' ? 'portfolio.stockHoldings.totalPnl' : `portfolio.${kind}`)}</dt>
        {[...totals].map(([currency, { realized, unrealized, cost }]) => (
          <dd key={currency} className="mt-0.5 font-semibold">
            <PnlAmount
              amount={kind === 'realized' ? realized : kind === 'unrealized' || unrealized === null ? unrealized : realized + unrealized}
              currency={currency} cost={kind === 'unrealized' ? cost : null}
            />
          </dd>
        ))}
      </div>
    ))}
  </dl>
}

type HoldingTrade = { wallet: StockWalletHolding; trade: StockWalletHolding['trades'][number] }
type HoldingColumn = 'date' | 'sourceWallet' | 'side' | 'quantity' | 'price' | 'fees' | 'stockHoldings.remaining' | 'realized' | 'unrealized'
const tradeSortDir = (key: HoldingColumn) => key === 'sourceWallet' || key === 'side' ? 'asc' : 'desc'

function TradeHistory({ wallets, price }: { wallets: StockWalletHolding[]; price: StockPrice }) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const { sort, onHeaderSort } = useTableSort<HoldingColumn>({ key: 'date', dir: 'desc' }, tradeSortDir)
  const trades = open ? wallets.flatMap(wallet => wallet.trades.map(trade => ({ wallet, trade }))) : []
  const compareInPln = trades.some(({ trade }) => majorCurrency(trade.currency) !== majorCurrency(trades[0].trade.currency))
  const amount = (value: number | null, currency: string) => value === null ? null
    : compareInPln ? toPln(value, currency) : inMajorUnits(value, currency)
  const columns: SortColumns<HoldingTrade, HoldingColumn> = {
    date: ({ trade }) => Date.parse(trade.executedAt ?? trade.date),
    sourceWallet: ({ wallet }) => wallet.name,
    side: ({ trade }) => t('portfolio.' + trade.side),
    quantity: ({ trade }) => Number(trade.quantity),
    price: ({ trade }) => amount(Number(trade.price), trade.currency),
    fees: ({ trade }) => amount(Number(trade.fees), trade.currency),
    'stockHoldings.remaining': ({ trade }) => trade.remainingQuantity,
    realized: ({ trade }) => amount(trade.realizedPnl, trade.currency),
    unrealized: ({ trade }) => trade.side === 'buy'
      ? amount(openPnl(trade.remainingQuantity, trade.costBasis, trade.currency, price), majorCurrency(trade.currency))
      : null,
  }
  const rows = sortTableRows(trades, sort, columns, i18n.language)
  const formatQuantity = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 }).format
  const formatPrice = new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 8 }).format
  const formatTime = new Intl.DateTimeFormat(i18n.language, {
    timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit',
  }).format

  return (
    <details className="mt-4 rounded-md border border-slate-800" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer rounded-md px-3 py-2 text-sm font-medium hover:bg-slate-800/50">
        {t('portfolio.transactions')}
      </summary>
      {open && <>
        {wallets.some(wallet => wallet.reconciled) && (
          <p className="px-3 py-2 text-xs text-slate-400">{t('portfolio.stockHoldings.snapshotNote')}</p>
        )}
        {rows.length ? (
          <div className="overflow-x-auto">
            <table aria-label={t('portfolio.transactions')} className="w-full whitespace-nowrap text-left text-sm tabular-nums">
              <caption className="caption-bottom px-3 py-2 text-left text-xs text-slate-400">
                {t('portfolio.stockHoldings.realizedNote')}
              </caption>
              <thead className="text-xs text-slate-400">
                <tr>
                  {(Object.keys(columns) as HoldingColumn[]).map(key => (
                    <SortHeader key={key} col={key} label={t('portfolio.' + key)} sort={sort} onSort={onHeaderSort} compact />
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(({ wallet, trade }) => {
                    const buy = trade.side === 'buy'
                    const currency = majorCurrency(trade.currency)
                    const unrealized = openPnl(trade.remainingQuantity, trade.costBasis, trade.currency, price)
                    const realized = trade.realizedPnl === null ? null : inMajorUnits(trade.realizedPnl, trade.currency)
                    const cost = trade.costBasis === null ? null : inMajorUnits(trade.costBasis, trade.currency)
                    const soldCost = trade.realizedCostBasis === null ? null : inMajorUnits(trade.realizedCostBasis, trade.currency)
                    return <tr key={`${wallet.id}:${trade.id}`} className="border-t border-slate-800">
                      <td className="px-3 py-2">
                        <time dateTime={trade.executedAt ?? trade.date}>
                          {trade.date}{trade.executedAt && ` ${formatTime(new Date(trade.executedAt))}`}
                        </time>
                      </td>
                      <td className="px-3 py-2">{wallet.name}</td>
                      <td className="px-3 py-2">{t(`portfolio.${trade.side}`)}</td>
                      <td className="px-3 py-2">{formatQuantity(Number(trade.quantity))}</td>
                      <td className="px-3 py-2">{formatPrice(Number(trade.price))} {currencyLabel(trade.currency)}</td>
                      <td className="px-3 py-2">{fmtMoney(Number(trade.fees), trade.currency)}</td>
                      <td className="px-3 py-2">{trade.remainingQuantity === null ? '—' : formatQuantity(trade.remainingQuantity)}</td>
                      <td className="px-3 py-2"><PnlAmount amount={realized} currency={currency} cost={soldCost} /></td>
                      <td className="px-3 py-2">{buy ? <PnlAmount amount={unrealized} currency={currency} cost={cost} /> : '—'}</td>
                    </tr>
                  })}
              </tbody>
            </table>
          </div>
        ) : <p className="px-3 py-2 text-sm text-slate-400">{t('portfolio.emptyTransactions')}</p>}
      </>}
    </details>
  )
}

export function StockHoldingsCard({ holdings, quote, onRetry }: StockHoldingsProps) {
  const { t, i18n } = useTranslation()
  const formatQuantity = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 }).format
  const lastPrice = quote?.lastPrice
  const currency = currencyLabel(quote?.currency)
  const valueCurrency = majorCurrency(currency)
  const unitValue = lastPrice != null && Number.isFinite(lastPrice) && lastPrice > 0
    ? inMajorUnits(lastPrice, currency)
    : null
  const price = { currency: valueCurrency, unitValue }

  return (
    <section aria-label={t('portfolio.stockHoldings.title')}>
      <CollapsibleCard
        title={t('portfolio.stockHoldings.title')}
        heading="h2"
        actions={
          <Link to="/portfolio" className="text-sm text-emerald-400 hover:underline">
            {t('portfolio.title')}
          </Link>
        }
      >
        {holdings === null ? (
          <p role="status" className="text-sm text-slate-400">{t('portfolio.stockHoldings.loading')}</p>
        ) : holdings === 'error' ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <p role="alert" className="text-slate-400">{t('portfolio.stockHoldings.error')}</p>
            <button type="button" className="text-emerald-400 hover:underline" onClick={onRetry}>{t('common.retry')}</button>
          </div>
        ) : holdings.wallets.length === 0 ? (
          <p className="text-sm text-slate-400">{t('portfolio.stockHoldings.empty')}</p>
        ) : (
          <>
            <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <div className="flex items-baseline gap-2">
                <dt className="text-sm text-slate-400">{t('portfolio.stockHoldings.total')}</dt>
                <dd className="text-lg font-semibold tabular-nums">{formatQuantity(holdings.quantity)}</dd>
              </div>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <dt className="text-sm text-slate-400">{t('portfolio.stockHoldings.marketValue')}</dt>
                {unitValue === null && holdings.quantity > 0 ? (
                  <dd className="text-sm text-slate-400">{t('portfolio.stockHoldings.valueUnavailable')}</dd>
                ) : (
                  <dd className="text-lg font-semibold tabular-nums">{fmtMoney(holdings.quantity * (unitValue ?? 0), valueCurrency)}</dd>
                )}
              </div>
            </dl>
            <div className="mt-3">
              <PnlSummary positions={holdings.wallets.flatMap(wallet => wallet.positions)} price={price} />
            </div>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {holdings.wallets.map(wallet => (
                <li key={wallet.id} className="rounded-md border border-slate-800 px-3 py-2 text-sm">
                  <div className="mb-2 flex items-baseline justify-between gap-3">
                    <span className="min-w-0 break-words text-slate-300">{wallet.name}</span>
                    <div className="shrink-0 text-right tabular-nums">
                      <p className="font-medium">{wallet.quantity ? formatQuantity(wallet.quantity) : t('portfolio.closed')}</p>
                      {wallet.quantity > 0 && unitValue !== null && (
                        <p className="text-xs text-slate-400">{fmtMoney(wallet.quantity * unitValue, valueCurrency)}</p>
                      )}
                    </div>
                  </div>
                  <PnlSummary positions={wallet.positions} price={price} />
                </li>
              ))}
            </ul>
            <TradeHistory wallets={holdings.wallets} price={price} />
          </>
        )}
      </CollapsibleCard>
    </section>
  )
}
