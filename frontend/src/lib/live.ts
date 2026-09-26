// Today's live prices — how the pages talk about them.
//
// While an exchange trades, the backend downloads every tracked stock's session
// so far once an hour (backend `app/services/live_prices.py`) and lays it over
// the finished-session figures: a row's `lastPrice` and `priceChangePct` become
// today's, and its `live` object says so. The analysis never moves with it —
// the rating, the signal and the method scores stay the last FINISHED
// session's, because an unfinished day has only part of its volume and VSA
// reads low volume as a signal. These helpers let a page say both halves of
// that out loud.

import type { ApiLivePrice } from '../api/stocksApi'
import { GPW_MARKET, MARKET_CODES } from './markets'

/** Anything that may carry a live price: a ranking row, a heatmap tile. */
export interface LiveRow {
  market?: string
  lastSession?: string | null
  live?: ApiLivePrice | null
}

export interface LiveMarket {
  market: string
  /** The newest trade time among the market's live rows (ISO). */
  asOf: string
}

export interface LiveSummary {
  /** Markets with live prices on the page, in the app's market order. */
  markets: LiveMarket[]
  /** The finished session the analysis of those rows comes from (YYYY-MM-DD). */
  finishedSession: string | null
}

/** The app's market order (the registry's display order). */
const MARKET_ORDER = Object.keys(MARKET_CODES)

/**
 * Which markets on the page show live prices, and as of when. `null` when no
 * row carries one — outside trading hours, and on an older backend.
 */
export function liveSummary(rows: readonly LiveRow[]): LiveSummary | null {
  const newest = new Map<string, string>()
  let finished: string | null = null
  for (const row of rows) {
    const live = row.live
    if (!live) continue
    const market = row.market ?? GPW_MARKET
    const seen = newest.get(market)
    // ISO timestamps in one zone (UTC, as the API sends them) sort as text.
    if (!seen || live.asOf > seen) newest.set(market, live.asOf)
    if (row.lastSession && (!finished || row.lastSession > finished)) {
      finished = row.lastSession
    }
  }
  if (newest.size === 0) return null
  const rank = (m: string) => {
    const i = MARKET_ORDER.indexOf(m)
    return i < 0 ? MARKET_ORDER.length : i
  }
  const markets = [...newest.entries()]
    .map(([market, asOf]) => ({ market, asOf }))
    .sort((a, b) => rank(a.market) - rank(b.market))
  return { markets, finishedSession: finished }
}

const sameLocalDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate()

/**
 * The time a live price is from: "14:44" today, "23.09 17:04" on another day
 * (a stock that has not traded yet today still carries yesterday's last trade).
 * In the reader's own clock, like every other time the app shows.
 */
export function fmtLiveTime(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const time = d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  if (sameLocalDay(d, now)) return time
  const day = d.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })
  return `${day} ${time}`
}

/** A session date "2026-09-23" as "23.09" — how the notes name the day. */
export function fmtSessionDay(day: string): string {
  const [, month, date] = day.split('-')
  return month && date ? `${date}.${month}` : day
}

/** True when the stock has not traded yet today (its price is yesterday's close). */
export function notTradedYet(live: ApiLivePrice): boolean {
  return live.volume === 0
}
