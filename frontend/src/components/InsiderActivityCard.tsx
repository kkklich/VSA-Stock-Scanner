// Insider buying and selling card (MAR Art. 19 ESPI reports for GPW; Yahoo
// Finance / SEC Form 4 for US & UK listings). Summarizes open-market purchases
// vs sales, net share/value balance, and lists recent filings with links to
// the primary source.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ExternalLink, Loader2, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react'
import { Card, CardTitle, InfoTip } from './ui'
import type { ApiInsiderTransactionsResponse } from '../api/stocksApi'
import { fmtMoney, safeHttpUrl } from '../lib/format'

const INITIAL_VISIBLE_ROWS = 8

function fmtShares(n: number | null | undefined): string {
  if (n == null || n === 0) return '—'
  return n.toLocaleString()
}

export function InsiderActivityCard({
  data,
  loading,
  includeAll,
  onToggleIncludeAll,
}: {
  data: ApiInsiderTransactionsResponse | null
  loading: boolean
  includeAll: boolean
  onToggleIncludeAll: (next: boolean) => void
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  const summary = data?.summary
  const transactions = data?.transactions ?? []
  const currency = summary?.currency ?? data?.currency ?? 'PLN'
  const visibleRows = expanded
    ? transactions
    : transactions.slice(0, INITIAL_VISIBLE_ROWS)

  const netPositive =
    (summary?.netValue ?? 0) > 0 ||
    ((summary?.netValue ?? 0) === 0 && (summary?.netShares ?? 0) > 0)
  const netNegative =
    (summary?.netValue ?? 0) < 0 ||
    ((summary?.netValue ?? 0) === 0 && (summary?.netShares ?? 0) < 0)

  return (
    <Card className="p-4">
      <div data-testid="insider-activity-card">
        <CardTitle
          right={
            <div className="flex items-center gap-3">
              {loading && (
                <Loader2 size={14} className="animate-spin text-slate-500" />
              )}
              <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-normal normal-case tracking-normal text-slate-400 hover:text-slate-200">
                <input
                  type="checkbox"
                  checked={includeAll}
                  onChange={(e) => onToggleIncludeAll(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-900 accent-emerald-500"
                />
                <span>{t('insider.includeAllToggle')}</span>
              </label>
            </div>
          }
        >
          {t('insider.title')} <InfoTip text={t('insider.info')} />
        </CardTitle>
      </div>

      <p className="mt-1.5 text-xs text-slate-500">{t('insider.asymmetryNote')}</p>

      {summary && (summary.totalPurchasesCount > 0 || summary.totalSalesCount > 0 || transactions.length > 0) ? (
        <>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {/* Purchases */}
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
              <div className="flex items-center justify-between text-xs font-medium text-emerald-400">
                <span>{t('insider.purchases')}</span>
                <TrendingUp size={14} />
              </div>
              <div className="mt-1 text-base font-semibold tabular-nums text-emerald-300">
                {summary.totalPurchasesValue > 0
                  ? fmtMoney(summary.totalPurchasesValue, currency)
                  : `${fmtShares(summary.totalPurchasesShares)} ${t('insider.sharesUnit')}`}
              </div>
              <div className="mt-0.5 text-[11px] tabular-nums text-slate-400">
                {t('insider.tradesAndShares', {
                  count: summary.totalPurchasesCount,
                  shares: fmtShares(summary.totalPurchasesShares),
                })}
              </div>
            </div>

            {/* Sales */}
            <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
              <div className="flex items-center justify-between text-xs font-medium text-rose-400">
                <span>{t('insider.sales')}</span>
                <TrendingDown size={14} />
              </div>
              <div className="mt-1 text-base font-semibold tabular-nums text-rose-300">
                {summary.totalSalesValue > 0
                  ? fmtMoney(summary.totalSalesValue, currency)
                  : `${fmtShares(summary.totalSalesShares)} ${t('insider.sharesUnit')}`}
              </div>
              <div className="mt-0.5 text-[11px] tabular-nums text-slate-400">
                {t('insider.tradesAndShares', {
                  count: summary.totalSalesCount,
                  shares: fmtShares(summary.totalSalesShares),
                })}
              </div>
            </div>

            {/* Net Balance */}
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between text-xs font-medium text-slate-400">
                <span>{t('insider.netBalance')}</span>
                <span
                  className={
                    'rounded px-1.5 py-0.5 text-[10px] font-semibold ' +
                    (netPositive
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : netNegative
                        ? 'bg-rose-500/20 text-rose-300'
                        : 'bg-slate-800 text-slate-400')
                  }
                >
                  {netPositive
                    ? t('insider.netBuying')
                    : netNegative
                      ? t('insider.netSelling')
                      : t('insider.netNeutral')}
                </span>
              </div>
              <div
                className={
                  'mt-1 text-base font-semibold tabular-nums ' +
                  (netPositive
                    ? 'text-emerald-400'
                    : netNegative
                      ? 'text-rose-400'
                      : 'text-slate-300')
                }
              >
                {summary.netValue !== 0
                  ? `${summary.netValue > 0 ? '+' : ''}${fmtMoney(summary.netValue, currency)}`
                  : `${summary.netShares > 0 ? '+' : ''}${fmtShares(summary.netShares)} ${t('insider.sharesUnit')}`}
              </div>
              <div className="mt-0.5 text-[11px] tabular-nums text-slate-400">
                {t('insider.netSharesLabel', {
                  shares: `${summary.netShares > 0 ? '+' : ''}${fmtShares(summary.netShares)}`,
                })}
              </div>
            </div>
          </div>

          {/* Transactions Table */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="pb-2 pr-3 font-semibold">{t('insider.colDate')}</th>
                  <th className="pb-2 pr-3 font-semibold">{t('insider.colRole')}</th>
                  <th className="pb-2 pr-3 font-semibold">{t('insider.colType')}</th>
                  <th className="pb-2 pr-3 text-right font-semibold">{t('insider.colShares')}</th>
                  <th className="pb-2 pr-3 text-right font-semibold">{t('insider.colPrice')}</th>
                  <th className="pb-2 pr-3 text-right font-semibold">{t('insider.colValue')}</th>
                  <th className="pb-2 text-right font-semibold">{t('insider.colSource')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {visibleRows.map((tx, idx) => {
                  const isBuy = tx.transactionType === 'buy'
                  const isSell = tx.transactionType === 'sell'
                  const txCurrency = tx.currency ?? currency
                  const safeUrl = safeHttpUrl(tx.sourceUrl)
                  const typeBadgeClass = isBuy
                    ? 'bg-emerald-500/20 text-emerald-300'
                    : isSell
                      ? 'bg-rose-500/20 text-rose-300'
                      : 'bg-slate-800 text-slate-400'

                  return (
                    <tr key={`${tx.publicationDate}-${idx}`} className="hover:bg-slate-900/40">
                      <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-slate-300">
                        {tx.publicationDate}
                      </td>
                      <td className="py-2 pr-3 text-slate-200">
                        <div className="font-medium">
                          {tx.role || tx.insiderName || t('insider.defaultRole')}
                        </div>
                        {tx.role && tx.insiderName && (
                          <div className="text-[11px] text-slate-500">{tx.insiderName}</div>
                        )}
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3">
                        <span
                          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${typeBadgeClass}`}
                        >
                          {t(`insider.type.${tx.transactionType}`, {
                            defaultValue: tx.transactionType,
                          })}
                        </span>
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3 text-right tabular-nums text-slate-300">
                        {fmtShares(tx.shares)}
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3 text-right tabular-nums text-slate-300">
                        {tx.price != null && tx.price > 0
                          ? fmtMoney(tx.price, txCurrency)
                          : '—'}
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3 text-right font-medium tabular-nums text-slate-200">
                        {tx.value != null && tx.value > 0
                          ? fmtMoney(tx.value, txCurrency)
                          : '—'}
                      </td>
                      <td className="whitespace-nowrap py-2 text-right">
                        {safeUrl ? (
                          <a
                            href={safeUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-emerald-400 hover:underline"
                          >
                            <span>{tx.source.toUpperCase()}</span>
                            <ExternalLink size={11} />
                          </a>
                        ) : (
                          <span className="uppercase text-slate-500">{tx.source}</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {transactions.length > INITIAL_VISIBLE_ROWS && (
            <div className="mt-3 text-center">
              <button
                type="button"
                onClick={() => setExpanded((e) => !e)}
                className="text-xs font-medium text-emerald-400 hover:text-emerald-300"
              >
                {expanded
                  ? t('insider.showLess')
                  : t('insider.showAll', { count: transactions.length })}
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-800/80 bg-slate-900/40 px-3 py-3 text-xs text-slate-400">
          <ShieldAlert size={15} className="shrink-0 text-slate-500" />
          <span>{loading ? t('insider.loading') : t('insider.empty')}</span>
        </div>
      )}
    </Card>
  )
}
