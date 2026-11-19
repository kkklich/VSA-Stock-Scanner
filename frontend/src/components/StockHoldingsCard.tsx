import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { portfolioRequest, type StockHoldings } from '../api/portfoliosApi'
import { useAuth } from '../hooks/useAuth'
import { Card } from './ui'

export function StockHoldingsCard({ ticker }: { ticker: string }) {
  const { user, loading } = useAuth()
  if (loading || !user) return null
  return <AccountStockHoldings key={`${user.id}:${ticker}`} ticker={ticker} owner={user.id} />
}

function AccountStockHoldings({ ticker, owner }: { ticker: string; owner: number }) {
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

  return (
    <section aria-label={t('portfolio.stockHoldings.title')}>
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">{t('portfolio.stockHoldings.title')}</h2>
          <Link to="/portfolio" className="text-sm text-emerald-400 hover:underline">
            {t('portfolio.title')}
          </Link>
        </div>
        {holdings === null ? (
          <p role="status" className="mt-2 text-sm text-slate-400">{t('portfolio.stockHoldings.loading')}</p>
        ) : holdings === 'error' ? (
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
            <p role="alert" className="text-slate-400">{t('portfolio.stockHoldings.error')}</p>
            <button type="button" className="text-emerald-400 hover:underline" onClick={() => {
              setHoldings(null)
              setAttempt(previous => previous + 1)
            }}>{t('common.retry')}</button>
          </div>
        ) : holdings.wallets.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">{t('portfolio.stockHoldings.empty')}</p>
        ) : (
          <>
            <dl className="mt-2 flex items-baseline gap-2">
              <dt className="text-sm text-slate-400">{t('portfolio.stockHoldings.total')}</dt>
              <dd className="text-lg font-semibold tabular-nums">{formatQuantity(holdings.quantity)}</dd>
            </dl>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {holdings.wallets.map(wallet => (
                <li key={wallet.id} className="flex items-baseline justify-between gap-3 rounded-md border border-slate-800 px-3 py-2 text-sm">
                  <span className="min-w-0 break-words text-slate-300">{wallet.name}</span>
                  <span className="shrink-0 font-medium tabular-nums">{formatQuantity(wallet.quantity)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
    </section>
  )
}
