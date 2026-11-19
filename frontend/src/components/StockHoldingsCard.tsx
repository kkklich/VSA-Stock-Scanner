import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { portfolioRequest, type StockHoldings } from '../api/portfoliosApi'
import type { ApiStockSignals } from '../api/stocksApi'
import { useAuth } from '../hooks/useAuth'
import { currencyLabel, fmtMoney, majorCurrency } from '../lib/format'
import { CollapsibleCard } from './ui'

interface StockHoldingsProps {
  ticker: string
  quote?: Pick<ApiStockSignals, 'lastPrice' | 'currency'> | null
}

export function StockHoldingsCard({ ticker, quote }: StockHoldingsProps) {
  const { user, loading } = useAuth()
  if (loading || !user) return null
  return <AccountStockHoldings key={`${user.id}:${ticker}`} ticker={ticker} quote={quote} owner={user.id} />
}

function AccountStockHoldings({ ticker, quote, owner }: StockHoldingsProps & { owner: number }) {
  const { t, i18n } = useTranslation()
  const [holdings, setHoldings] = useState<StockHoldings | 'error' | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const request = new AbortController()
    portfolioRequest<StockHoldings>('GET', `/holdings/${encodeURIComponent(ticker)}`, undefined, request.signal, owner)
      .then(result => { if (!request.signal.aborted) setHoldings(result) })
      .catch(() => { if (!request.signal.aborted) setHoldings('error') })
    return () => request.abort()
  }, [ticker, owner, attempt])

  const formatQuantity = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 }).format
  const price = quote?.lastPrice
  const quotedInPence = currencyLabel(quote?.currency) === 'GBX'
  const valueCurrency = majorCurrency(quote?.currency)
  const unitValue = price != null && Number.isFinite(price) && price > 0
    ? price / (quotedInPence ? 100 : 1)
    : null

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
            <button type="button" className="text-emerald-400 hover:underline" onClick={() => {
              setHoldings(null)
              setAttempt(previous => previous + 1)
            }}>{t('common.retry')}</button>
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
                {unitValue === null ? (
                  <dd className="text-sm text-slate-400">{t('portfolio.stockHoldings.valueUnavailable')}</dd>
                ) : (
                  <dd className="text-lg font-semibold tabular-nums">{fmtMoney(holdings.quantity * unitValue, valueCurrency)}</dd>
                )}
              </div>
            </dl>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {holdings.wallets.map(wallet => (
                <li key={wallet.id} className="flex items-baseline justify-between gap-3 rounded-md border border-slate-800 px-3 py-2 text-sm">
                  <span className="min-w-0 break-words text-slate-300">{wallet.name}</span>
                  <div className="shrink-0 text-right tabular-nums">
                    <p className="font-medium">{formatQuantity(wallet.quantity)}</p>
                    {unitValue !== null && (
                      <p className="text-xs text-slate-400">{fmtMoney(wallet.quantity * unitValue, valueCurrency)}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </CollapsibleCard>
    </section>
  )
}
