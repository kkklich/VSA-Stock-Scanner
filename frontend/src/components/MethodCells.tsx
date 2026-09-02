// Cell renderers for the dashboard's per-method columns and the combined
// cross-method summary column. A method cell shows the method's 0–100 score
// (colored by the shared rating bands) plus a small "recent example" chip when
// the setup fired lately — the yes/no-and-how-recent indicator the framework
// exposes per row.

import type { MethodResult } from '../types'
import { ratingTone } from '../lib/format'

/** Show the recency chip only when the setup fired within this many days. */
const RECENT_DAYS = 15

/** A small chip saying how recently the method's setup last fired. */
function RecencyChip({ result }: { result: MethodResult }) {
  if (result.fired) {
    return (
      <span className="rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide ring-1 bg-emerald-500/15 text-emerald-400 ring-emerald-500/30">
        ▲ now
      </span>
    )
  }
  if (result.daysSince !== 999 && result.daysSince <= RECENT_DAYS) {
    return (
      <span className="rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide ring-1 bg-amber-500/10 text-amber-300 ring-amber-500/30">
        ▲ {result.daysSince}d
      </span>
    )
  }
  return null
}

/**
 * One per-method cell: the method's score for this stock plus a recent-example
 * chip. Renders a muted dash when the stock has too little history to evaluate
 * the method (or the row carries no result for it).
 */
export function MethodScoreCell({ result }: { result: MethodResult | undefined }) {
  if (!result || !result.available) {
    return <span className="text-slate-600">—</span>
  }
  const tone = ratingTone(result.score)
  return (
    <span
      className="inline-flex items-center justify-end gap-1.5"
      title={result.detail ?? undefined}
    >
      <RecencyChip result={result} />
      <span className={'w-7 text-right text-sm font-semibold tabular-nums ' + tone.text}>
        {result.score}
      </span>
    </span>
  )
}

/**
 * The combined cross-method summary cell: the mean of the selected methods'
 * scores, drawn as a number + thin meter (like the VSA rating). A dash when the
 * row could evaluate none of the selected methods.
 */
export function CombinedScoreCell({ score }: { score: number | null }) {
  if (score === null) return <span className="text-slate-600">—</span>
  const tone = ratingTone(score)
  return (
    <div className="flex items-center gap-2.5">
      <span className={'w-7 text-sm font-semibold tabular-nums ' + tone.text}>
        {score}
      </span>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-700/60">
        <div className={'h-full rounded-full ' + tone.bar} style={{ width: `${score}%` }} />
      </div>
    </div>
  )
}
