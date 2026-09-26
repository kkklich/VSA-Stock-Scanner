// The Dashboard's top-down read of the market: how the verdicts split (breadth)
// and which stocks' VSA rating rose or fell the most since the previous
// session. Fed by GET /api/stocks/market-overview, which only tallies the same
// ranking rows the list below shows — so it can never disagree with that list.
//
// It counts and does not conclude: there is no single "market score" here,
// because a verdict split cannot tell an early move from a late one.

import { useTranslation } from 'react-i18next'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import type { ApiMarketBreadth, ApiRatingMover } from '../api/stocksApi'
import { useMarketOverview } from '../hooks/useMarketOverview'
import { Card, CardTitle, CompanyLink, InfoTip, MarketBadge } from './ui'
import { SessionNote } from './SessionNote'
import { ALL_MARKETS, displayTicker } from '../lib/markets'
import { ratingTone } from '../lib/format'

/** The five verdicts, most bullish on the left. */
const SEGMENTS = [
  { key: 'strongBuy', verdict: 'Strong Buy', color: 'bg-emerald-500' },
  { key: 'buy', verdict: 'Buy', color: 'bg-emerald-500/50' },
  { key: 'hold', verdict: 'Hold', color: 'bg-slate-500/60' },
  { key: 'sell', verdict: 'Sell', color: 'bg-rose-500/50' },
  { key: 'strongSell', verdict: 'Strong Sell', color: 'bg-rose-500' },
] as const

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'up' | 'down'
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="leading-tight text-slate-500">{label}</dt>
      <dd
        className={
          'font-semibold tabular-nums ' +
          (value === 0
            ? 'text-slate-400'
            : tone === 'up'
              ? 'text-emerald-400'
              : 'text-rose-400')
        }
      >
        {value}
      </dd>
    </div>
  )
}

function BreadthCard({ breadth }: { breadth: ApiMarketBreadth }) {
  const { t } = useTranslation()
  const total = breadth.total

  return (
    <Card>
      <CardTitle right={<InfoTip text={t('overview.breadthInfo')} />}>
        {t('overview.breadth')}
      </CardTitle>
      <div className="flex flex-col gap-3 px-4 pb-4">
        {/* Verdict split — one bar, five segments. The legend below repeats
            every number in text, so the bar is never the only carrier. */}
        <div
          role="img"
          aria-label={t('overview.splitAria', {
            bullish: breadth.bullishPct,
            bearish: breadth.bearishPct,
          })}
          className="flex h-3 w-full overflow-hidden rounded-full bg-slate-800"
        >
          {SEGMENTS.map(({ key, verdict, color }) =>
            breadth[key] > 0 ? (
              <div
                key={key}
                className={color}
                style={{ width: `${(100 * breadth[key]) / total}%` }}
                title={`${verdict}: ${breadth[key]}`}
              />
            ) : null,
          )}
        </div>

        <div className="flex items-baseline justify-between text-sm">
          <span className="font-semibold tabular-nums text-emerald-400">
            {t('overview.bullish', { pct: breadth.bullishPct })}
          </span>
          <span className="font-semibold tabular-nums text-rose-400">
            {t('overview.bearish', { pct: breadth.bearishPct })}
          </span>
        </div>

        <dl className="grid grid-cols-5 gap-1 text-center">
          {SEGMENTS.map(({ key, verdict, color }) => (
            <div key={key} className="min-w-0">
              <dt className="flex flex-col items-center gap-0.5 text-[10px] uppercase leading-tight tracking-wide text-slate-500">
                <span className={'h-1.5 w-1.5 shrink-0 rounded-full ' + color} />
                <span>{verdict}</span>
              </dt>
              <dd className="text-sm font-semibold tabular-nums text-slate-200">
                {breadth[key]}
              </dd>
            </div>
          ))}
        </dl>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-slate-800 pt-3 text-xs">
          <Stat label={t('overview.advancers')} value={breadth.advancers} tone="up" />
          <Stat label={t('overview.decliners')} value={breadth.decliners} tone="down" />
          <Stat label={t('overview.ratingUp')} value={breadth.ratingUp} tone="up" />
          <Stat label={t('overview.ratingDown')} value={breadth.ratingDown} tone="down" />
          <Stat label={t('overview.newHighs')} value={breadth.new52wHighs} tone="up" />
          <Stat label={t('overview.newLows')} value={breadth.new52wLows} tone="down" />
        </dl>

        {breadth.averageRating !== null && (
          <p className="text-xs text-slate-500">
            {t('overview.averageRating')}{' '}
            <span
              className={
                'font-semibold tabular-nums ' + ratingTone(breadth.averageRating).text
              }
            >
              {breadth.averageRating.toFixed(1)}
            </span>
          </p>
        )}
      </div>
    </Card>
  )
}

function MoversCard({
  title,
  info,
  movers,
  direction,
  pooled,
}: {
  title: string
  info: string
  movers: ApiRatingMover[]
  direction: 'up' | 'down'
  pooled: boolean
}) {
  const { t } = useTranslation()
  const Icon = direction === 'up' ? ArrowUpRight : ArrowDownRight
  const tone = direction === 'up' ? 'text-emerald-400' : 'text-rose-400'

  return (
    <Card>
      <CardTitle right={<InfoTip text={info} />}>
        <span className="inline-flex items-center gap-1.5">
          <Icon size={14} className={tone} />
          {title}
        </span>
      </CardTitle>
      {movers.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-slate-500">{t('overview.noMovers')}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-slate-800/70 px-4 pb-2">
          {movers.map((m) => (
            <li key={m.ticker} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <span className="flex items-center gap-1.5">
                  <CompanyLink
                    ticker={m.ticker}
                    title={m.name}
                    className="text-sm font-semibold text-slate-100"
                  >
                    {displayTicker(m.ticker)}
                  </CompanyLink>
                  {pooled && <MarketBadge market={m.market} />}
                </span>
                <p className="truncate text-xs text-slate-500">{m.name}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-sm tabular-nums">
                  <span className="text-slate-500">{m.previousRating}</span>
                  <span className="text-slate-600"> → </span>
                  <span className={'font-semibold ' + ratingTone(m.currentRating).text}>
                    {m.currentRating}
                  </span>
                </p>
                <p className={'text-xs font-semibold tabular-nums ' + tone}>
                  {m.ratingChange > 0 ? '+' : ''}
                  {m.ratingChange}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function MarketOverview({ market }: { market: string | null }) {
  const { t } = useTranslation()
  const { data, loading, error } = useMarketOverview(market)
  const pooled = market === ALL_MARKETS

  // A failure here must not take the ranking down with it — the overview is a
  // convenience on top of the list, so it steps aside quietly.
  if (error && !data) return null
  if (loading && !data) {
    return (
      <div aria-hidden className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-44 animate-pulse rounded-xl border border-slate-800 bg-slate-900/40"
          />
        ))}
      </div>
    )
  }
  if (!data || data.breadth.total === 0) return null

  return (
    <section aria-label={t('overview.heading')} className="flex flex-col gap-2">
      <SessionNote rows={[...data.moversUp, ...data.moversDown]} enabled={pooled} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <BreadthCard breadth={data.breadth} />
        <MoversCard
          title={t('overview.risers')}
          info={t('overview.risersInfo')}
          movers={data.moversUp}
          direction="up"
          pooled={pooled}
        />
        <MoversCard
          title={t('overview.fallers')}
          info={t('overview.fallersInfo')}
          movers={data.moversDown}
          direction="down"
          pooled={pooled}
        />
      </div>
    </section>
  )
}
