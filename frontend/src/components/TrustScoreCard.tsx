// Signal Trust Score card (stock detail page) — how accurate the VSA engine's
// strong calls have proved on THIS stock. The backend back-tests every
// historical Strong Buy / Strong Sell signal (forward return vs. the stock's
// own baseline move) and folds the results into one 0–100 score. Computed
// locally by app/analysis/trust_score.py; no external AI services involved.

import { useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, ShieldCheck } from 'lucide-react'
import { Card, CardTitle, InfoTip } from './ui'
import { useTrustScore } from '../hooks/useTrustScore'
import type { ApiTrustScore, ApiTrustScoreEvent } from '../api/stocksApi'

/** Badge label + colouring per grade — emerald = reliable, rose = unreliable. */
const GRADE_STYLE: Record<
  ApiTrustScore['grade'],
  { label: string; badge: string; text: string; bar: string }
> = {
  high: {
    label: 'Reliable',
    badge: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
    text: 'text-emerald-400',
    bar: 'bg-emerald-500/70',
  },
  medium: {
    label: 'Mixed record',
    badge: 'bg-amber-500/15 text-amber-400 ring-amber-500/30',
    text: 'text-amber-400',
    bar: 'bg-amber-500/70',
  },
  low: {
    label: 'Unreliable',
    badge: 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
    text: 'text-rose-400',
    bar: 'bg-rose-500/70',
  },
  insufficient: {
    label: 'No track record',
    badge: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
    text: 'text-slate-300',
    bar: 'bg-slate-500/70',
  },
}

function EventRow({ e }: { e: ApiTrustScoreEvent }) {
  const bullish = e.verdict === 'Strong Buy'
  return (
    <li className="py-2">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          <span
            className={
              'grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold ' +
              (e.goodEntry
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-rose-500/15 text-rose-400')
            }
            title={e.goodEntry ? 'Good entry' : 'Bad entry'}
          >
            {e.goodEntry ? '✓' : '✕'}
          </span>
          <span className="text-slate-200">{e.signalName}</span>
          <span
            className={
              'text-[10px] font-semibold ' +
              (bullish ? 'text-emerald-500/80' : 'text-rose-500/80')
            }
          >
            {e.verdict}
          </span>
        </span>
        <span className="text-xs tabular-nums text-slate-500">{e.date}</span>
      </div>
      <p className="mt-1 pl-6 text-xs leading-relaxed text-slate-400">
        Price moved {e.forwardReturnPct >= 0 ? '+' : ''}
        {e.forwardReturnPct.toFixed(1)}% afterwards —{' '}
        {e.excessReturnPct >= 0 ? 'beat' : 'lagged'} the stock's typical move (
        {e.baselineReturnPct >= 0 ? '+' : ''}
        {e.baselineReturnPct.toFixed(1)}%) by{' '}
        {Math.abs(e.excessReturnPct).toFixed(1)} pp.
      </p>
    </li>
  )
}

export function TrustScoreCard({ ticker }: { ticker: string }) {
  const { data, loading, error } = useTrustScore(ticker)
  const [showEvents, setShowEvents] = useState(false)

  const style = data ? GRADE_STYLE[data.grade] : GRADE_STYLE.insufficient
  // "insufficient" covers two cases: no judged signals at all, and a sample
  // too small (1–7) for a numeric score — the badge must not claim "No track
  // record" while the card shows e.g. "4/6 good entries" next to it.
  const badgeLabel =
    data && data.grade === 'insufficient' && data.evaluatedCount > 0
      ? 'Too few signals'
      : style.label

  return (
    <Card>
      <CardTitle>
        <span className="inline-flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-emerald-400" /> Signal Trust Score
        </span>{' '}
        <InfoTip text="How accurate the VSA engine's strong calls have been on THIS stock. Every past Strong Buy / Strong Sell signal is replayed as a paper trade: did the price beat the stock's typical 10-session move in the signal's direction? The hit-rate and the median edge are combined into one 0–100 score (few signals = pulled toward the neutral 50). Computed locally; deterministic and free." />
      </CardTitle>

      <div className="px-4 pb-4">
        {loading && !data && (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <Loader2 size={14} className="animate-spin" /> Back-testing signals…
          </div>
        )}

        {error && !data && (
          <p className="py-2 text-xs text-slate-500">
            Trust score unavailable: {error}
          </p>
        )}

        {data && (
          <>
            <div className="flex items-center gap-3">
              <div className="flex items-end gap-1">
                <span className={'text-4xl font-bold tabular-nums ' + style.text}>
                  {data.score ?? '—'}
                </span>
                {data.score != null && (
                  <span className="mb-1 text-xs text-slate-500">/ 100</span>
                )}
              </div>
              <div className="flex-1">
                <div className="mb-1 flex justify-between text-xs">
                  <span
                    className={
                      'rounded px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset ' +
                      style.badge
                    }
                  >
                    {badgeLabel}
                  </span>
                  {data.evaluatedCount > 0 && (
                    <span className="tabular-nums text-slate-400">
                      {data.goodCount}/{data.evaluatedCount} good entries
                    </span>
                  )}
                </div>
                <div className="h-1.5 rounded-full bg-slate-800">
                  <div
                    className={'h-1.5 rounded-full ' + style.bar}
                    style={{ width: `${data.score ?? 0}%` }}
                  />
                </div>
              </div>
            </div>

            {data.evaluatedCount > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-md bg-slate-900/60 px-2 py-1.5">
                  <span className="text-slate-500">Strong Buy</span>{' '}
                  <span className="float-right tabular-nums text-slate-300">
                    {data.buyEvaluated > 0
                      ? `${data.buyGood}/${data.buyEvaluated} good`
                      : '—'}
                  </span>
                </div>
                <div className="rounded-md bg-slate-900/60 px-2 py-1.5">
                  <span className="text-slate-500">Strong Sell</span>{' '}
                  <span className="float-right tabular-nums text-slate-300">
                    {data.sellEvaluated > 0
                      ? `${data.sellGood}/${data.sellEvaluated} good`
                      : '—'}
                  </span>
                </div>
              </div>
            )}

            <p className="mt-3 text-xs leading-relaxed text-slate-400">
              {data.summary}
            </p>

            {data.events.length > 0 && (
              <div className="mt-3 border-t border-slate-800 pt-2">
                <button
                  onClick={() => setShowEvents((s) => !s)}
                  className="flex w-full items-center justify-between py-1 text-xs font-medium text-slate-300 hover:text-slate-100"
                  aria-expanded={showEvents}
                >
                  Back-tested signals ({data.events.length})
                  {showEvents ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showEvents && (
                  <ul className="divide-y divide-slate-800/60">
                    {data.events.map((e) => (
                      <EventRow key={e.signalName + e.date} e={e} />
                    ))}
                  </ul>
                )}
              </div>
            )}

            <p className="mt-3 text-[10px] text-slate-600">
              {data.engine} · as of {data.asOf} · {data.horizonSessions}-session
              horizon · back-test of historical data, not investment advice
            </p>
          </>
        )}
      </div>
    </Card>
  )
}
