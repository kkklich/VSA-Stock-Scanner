// Today's live price, as the pages show it. The rules — what a live price is,
// and why it never moves a rating — live in `lib/live.ts`.
//
//  - LiveDot  — beside a price in a table or card: "this price is from today".
//  - LiveChip — in the stock page's header, with the time.
//  - LiveNote — one line above a list: which markets are live, as of when, and
//               that the ratings still come from the last finished session.
//
// Sky blue, not emerald: green already means "bullish" on every one of these
// screens, and a live price is news about time, not about direction.

import { useTranslation } from 'react-i18next'
import type { ApiLivePrice } from '../api/stocksApi'
import {
  fmtLiveTime,
  fmtSessionDay,
  liveSummary,
  notTradedYet,
  type LiveRow,
} from '../lib/live'

function useLiveTitle(live: ApiLivePrice): string {
  const { t } = useTranslation()
  const time = fmtLiveTime(live.asOf)
  return notTradedYet(live)
    ? t('live.titleNoTrade', { time })
    : t('live.title', { time })
}

/** A small dot after a live price; the tooltip says what it means. */
export function LiveDot({
  live,
  className = '',
}: {
  live: ApiLivePrice
  className?: string
}) {
  const title = useLiveTitle(live)
  return (
    <span
      role="img"
      aria-label={title}
      title={title}
      className={
        'inline-block h-1.5 w-1.5 shrink-0 rounded-full align-middle ' +
        // Hollow when the stock has not traded yet today: the price shown is
        // yesterday's close, carried over.
        (notTradedYet(live) ? 'ring-1 ring-inset ring-sky-400' : 'bg-sky-400') +
        (className ? ' ' + className : '')
      }
    />
  )
}

/** "● Today 14:44" beside the stock page's price. */
export function LiveChip({ live }: { live: ApiLivePrice }) {
  const { t } = useTranslation()
  const title = useLiveTitle(live)
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 rounded-md bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-400 ring-1 ring-inset ring-sky-500/30"
    >
      <span
        aria-hidden
        className={
          'h-1.5 w-1.5 rounded-full ' +
          (notTradedYet(live) ? 'ring-1 ring-inset ring-sky-400' : 'bg-sky-400')
        }
      />
      {notTradedYet(live)
        ? t('live.chipNoTrade')
        : t('live.chip', { time: fmtLiveTime(live.asOf) })}
    </span>
  )
}

/**
 * The note above a list that carries live prices: as of when, and that every
 * rating, signal and method score is still the last finished session's.
 * Renders nothing when no row is live (outside trading hours).
 */
export function LiveNote({
  rows,
  className = '',
}: {
  rows: readonly LiveRow[]
  className?: string
}) {
  const { t } = useTranslation()
  const summary = liveSummary(rows)
  if (!summary) return null
  const session = summary.finishedSession ? fmtSessionDay(summary.finishedSession) : '—'
  const text =
    summary.markets.length === 1
      ? t('live.noteOne', { time: fmtLiveTime(summary.markets[0].asOf), session })
      : t('live.noteMany', {
          markets: summary.markets
            .map((m) => `${t(`markets.short.${m.market}`)} ${fmtLiveTime(m.asOf)}`)
            .join(' · '),
          session,
        })
  return (
    <p
      className={
        'flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-400 ' +
        className
      }
    >
      <span aria-hidden className="mt-1 h-2 w-2 shrink-0 rounded-full bg-sky-400" />
      <span>{text}</span>
    </p>
  )
}
