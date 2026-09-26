// "Trade simulation · VSA V4" card for the stock-detail page.
//
// The owner's own VSA program (backend app/analysis/vsa4) replayed over this
// stock's stored history with the program's own simulator: every completed
// strength → test → confirmation sequence is entered at the next open with a
// structural stop and a 3R target, 1% of the account at risk, one position at
// a time. The card leads with the R figures (win rate, average R, profit
// factor) because those are what the rules are judged by; the account return
// is small by construction (1% risk, cash in between) and is shown beside
// buy & hold only as context. Data: GET /api/stocks/{ticker}/trade-simulation.

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { Card, CardTitle, InfoTip } from './ui'
import { useTradeSimulation } from '../hooks/useTradeSimulation'
import type {
  ApiEquityPoint,
  ApiSimulatedTrade,
  ApiTradeSimulation,
  SimulationSides,
} from '../api/stocksApi'
import { deltaTone, fmtPct } from '../lib/format'

/** Trades shown before "show all". */
const PREVIEW_TRADES = 5

// Equity sparkline geometry (SVG units; the SVG scales to the card width).
const W = 600
const H = 110
const PAD = { top: 8, right: 8, bottom: 18, left: 8 }

/** A price at a readable precision: penny stocks need four places. */
function fmtPrice(n: number): string {
  const digits = Math.abs(n) < 1 ? 4 : 2
  return n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const fmtR = (r: number): string => `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`

function Stat({
  label,
  value,
  sub,
  tone = 'text-slate-100',
}: {
  label: string
  value: string
  sub?: string
  tone?: string
}) {
  return (
    <div className="rounded-lg bg-slate-950/40 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={'text-lg font-semibold tabular-nums ' + tone}>{value}</div>
      {sub && <div className="text-[11px] tabular-nums text-slate-500">{sub}</div>}
    </div>
  )
}

function EquityCurve({
  points,
  initial,
  label,
  startLabel,
}: {
  points: ApiEquityPoint[]
  initial: number
  label: string
  startLabel: string
}) {
  const n = points.length
  const geometry = useMemo(() => {
    const values = points.map((p) => p.equity)
    const lo = Math.min(initial, ...values)
    const hi = Math.max(initial, ...values)
    const span = hi - lo || 1
    const x = (i: number) =>
      PAD.left + (n <= 1 ? 0 : (i / (n - 1)) * (W - PAD.left - PAD.right))
    const y = (v: number) =>
      PAD.top + (1 - (v - lo) / span) * (H - PAD.top - PAD.bottom)
    const path = points
      .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`)
      .join(' ')
    return { path, startY: y(initial) }
  }, [points, initial, n])

  if (n < 2) return null
  const up = points[n - 1].equity >= initial
  const stroke = up ? 'var(--color-emerald-500)' : 'var(--color-rose-500)'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label}>
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={geometry.startY}
        y2={geometry.startY}
        strokeDasharray="3 4"
        strokeWidth="1"
        className="stroke-slate-600"
      />
      <text x={W - PAD.right} y={geometry.startY - 4} textAnchor="end" fontSize="10" className="fill-slate-500">
        {startLabel}
      </text>
      <path d={geometry.path} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" />
      <text x={PAD.left} y={H - 4} fontSize="10" className="fill-slate-500">
        {points[0].date}
      </text>
      <text x={W - PAD.right} y={H - 4} textAnchor="end" fontSize="10" className="fill-slate-500">
        {points[n - 1].date}
      </text>
    </svg>
  )
}

function TradeRow({ trade }: { trade: ApiSimulatedTrade }) {
  const { t } = useTranslation()
  const open = trade.status === 'open'
  const r = trade.netR
  const won = trade.netPnl > 0
  return (
    <li className="py-2">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="flex min-w-0 items-center gap-2">
          <span
            className={
              'grid h-4 w-4 shrink-0 place-items-center rounded-full text-[10px] font-bold ' +
              (open
                ? 'bg-slate-500/20 text-slate-300'
                : won
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-rose-500/15 text-rose-400')
            }
            aria-hidden
          >
            {open ? '•' : won ? '✓' : '✕'}
          </span>
          <span className="shrink-0 text-xs tabular-nums text-slate-500">{trade.signalDate}</span>
          {/* Wraps rather than truncates: the test after the arrow is the point. */}
          <span className="min-w-0 text-slate-200">{trade.setup}</span>
          {trade.direction === 'short' && (
            <span className="shrink-0 rounded bg-rose-500/15 px-1.5 text-[10px] font-semibold text-rose-400">
              {t('chart.simulation.short')}
            </span>
          )}
        </span>
        {r != null && (
          <span className={'shrink-0 font-semibold tabular-nums ' + deltaTone(r)}>{fmtR(r)}</span>
        )}
      </div>
      <p className="mt-0.5 pl-6 text-xs tabular-nums text-slate-400">
        {fmtPrice(trade.entryPrice)} →{' '}
        {trade.exitPrice != null ? fmtPrice(trade.exitPrice) : '…'} ·{' '}
        {t(`chart.simulation.exit.${trade.exitReason}`, { defaultValue: trade.exitReason })}
        {trade.returnPct != null && (
          <span className={deltaTone(trade.returnPct)}> · {fmtPct(trade.returnPct)}</span>
        )}
        <span className="text-slate-500">
          {' '}
          ·{' '}
          {t('chart.simulation.levels', {
            stop: fmtPrice(trade.stopLoss),
            target: fmtPrice(trade.takeProfit),
          })}
        </span>
      </p>
    </li>
  )
}

function Results({ data }: { data: ApiTradeSimulation }) {
  const { t } = useTranslation()
  const [showAll, setShowAll] = useState(false)
  const trades = useMemo(() => [...data.trades].reverse(), [data.trades])
  const shown = showAll ? trades : trades.slice(0, PREVIEW_TRADES)
  const setups = data.sides === 'long' ? data.longSetups : data.longSetups + data.shortSetups

  if (setups === 0) {
    return <p className="py-2 text-sm text-slate-500">{t('chart.simulation.noSetups')}</p>
  }

  return (
    <>
      {/* Three columns at most: the card sits in the page's narrower left
          column (~570 px on a 1440 px screen), where six would wrap every tile. */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat
          label={t('chart.simulation.trades')}
          value={String(data.closedTrades)}
          sub={data.openTrades > 0 ? t('chart.simulation.openCount', { count: data.openTrades }) : undefined}
        />
        <Stat
          label={t('chart.simulation.winRate')}
          value={data.winRatePct != null ? `${data.winRatePct.toFixed(0)}%` : '—'}
          sub={t('chart.simulation.winRateSub', { wins: data.wins, losses: data.losses })}
        />
        <Stat
          label={t('chart.simulation.avgR')}
          value={data.avgR != null ? fmtR(data.avgR) : '—'}
          sub={t('chart.simulation.avgRSub')}
          tone={data.avgR != null ? deltaTone(data.avgR) : 'text-slate-100'}
        />
        <Stat
          label={t('chart.simulation.profitFactor')}
          value={data.profitFactor != null ? data.profitFactor.toFixed(2) : '—'}
          sub={t('chart.simulation.profitFactorSub')}
        />
        <Stat
          label={t('chart.simulation.account')}
          value={fmtPct(data.totalReturnPct)}
          sub={t('chart.simulation.accountSub', { dd: `${data.maxDrawdownPct.toFixed(1)}%` })}
          tone={deltaTone(data.totalReturnPct)}
        />
        <Stat
          label={t('chart.simulation.buyHold')}
          value={data.buyHoldReturnPct != null ? fmtPct(data.buyHoldReturnPct) : '—'}
          sub={t('chart.simulation.buyHoldSub')}
          tone="text-slate-300"
        />
      </div>

      <div className="mt-3">
        <EquityCurve
          points={data.equity}
          initial={data.initialCapital}
          label={t('chart.simulation.equityAria', { from: data.fromDate, to: data.asOf })}
          startLabel={t('chart.simulation.startLine')}
        />
      </div>

      <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
        <span>
          {t('chart.simulation.setups', { long: data.longSetups, short: data.shortSetups })}
        </span>
        {data.skippedEntries > 0 && (
          <span className="inline-flex items-center gap-1">
            · {t('chart.simulation.skipped', { count: data.skippedEntries })}
            <InfoTip text={t('chart.simulation.skippedInfo')} />
          </span>
        )}
      </p>

      {trades.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">{t('chart.simulation.noTrades')}</p>
      ) : (
        <div className="mt-3">
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {t('chart.simulation.tradeList')}
          </h4>
          <ul className="divide-y divide-slate-800">
            {shown.map((trade) => (
              <TradeRow key={`${trade.signalDate}-${trade.direction}`} trade={trade} />
            ))}
          </ul>
          {trades.length > PREVIEW_TRADES && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="mt-1 text-xs font-medium text-emerald-400 hover:underline"
            >
              {showAll
                ? t('chart.simulation.showLess')
                : t('chart.simulation.showAll', { count: trades.length })}
            </button>
          )}
        </div>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        {t('chart.simulation.assumptions', {
          risk: `${data.riskPct}%`,
          rr: data.rewardRisk,
          commission: `${data.commissionPct.toFixed(2)}%`,
          slippage: `${data.slippagePct.toFixed(2)}%`,
          from: data.fromDate,
          to: data.asOf,
          bars: data.barCount,
        })}
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{t('chart.simulation.note')}</p>
    </>
  )
}

export function TradeSimulationCard({ ticker }: { ticker: string }) {
  const { t } = useTranslation()
  const [sides, setSides] = useState<SimulationSides>('long')
  const { data, loading, error } = useTradeSimulation(ticker, sides)
  // Never show another stock's result while this one loads.
  const current = data && data.ticker === ticker.toUpperCase() ? data : null

  const toggle = (
    <div
      role="group"
      aria-label={t('chart.simulation.sidesLabel')}
      className="inline-flex rounded-md border border-slate-700 p-0.5 text-[11px]"
    >
      {(['long', 'both'] as const).map((s) => (
        <button
          key={s}
          type="button"
          aria-pressed={sides === s}
          onClick={() => setSides(s)}
          className={
            'rounded px-2 py-0.5 font-medium ' +
            (sides === s ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200')
          }
        >
          {s === 'long' ? t('chart.simulation.longOnly') : t('chart.simulation.longShort')}
        </button>
      ))}
    </div>
  )

  return (
    <Card>
      <CardTitle right={toggle}>
        {t('chart.simulation.title')} <InfoTip text={t('chart.simulation.info')} />
      </CardTitle>
      <div className="px-4 pb-4">
        {loading && !current && (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <Loader2 size={14} className="animate-spin" /> {t('chart.simulation.loading')}
          </div>
        )}
        {error && !current && (
          <p className="py-2 text-xs text-slate-500">{t('chart.simulation.error', { error })}</p>
        )}
        {current && (
          <div className={loading ? 'opacity-60 transition-opacity' : undefined}>
            <Results data={current} />
          </div>
        )}
      </div>
    </Card>
  )
}
