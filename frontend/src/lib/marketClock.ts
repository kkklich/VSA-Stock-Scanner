// Trading hours and nightly-refresh times per market, for the top bar's
// "Market: OPEN/CLOSED" light and its "Last sync" time.
//
// Hours are the exchange's own local time; the browser's time zone database
// (Intl) does the conversions, so daylight-saving changes are handled without a
// date library. Public holidays are not known — on a holiday the light says
// "open" during normal hours, which is the same simplification the page always
// made for the GPW.

import { GPW_MARKET } from './markets'

interface Session {
  timezone: string
  /** Continuous trading start and closing-auction end, minutes after midnight. */
  open: number
  close: number
  /** Which nightly run refreshes the market. */
  run: 'europe' | 'us'
}

const SESSIONS: Record<string, Session> = {
  gpw: { timezone: 'Europe/Warsaw', open: 9 * 60, close: 17 * 60 + 5, run: 'europe' },
  us: { timezone: 'America/New_York', open: 9 * 60 + 30, close: 16 * 60, run: 'us' },
  de: { timezone: 'Europe/Berlin', open: 9 * 60, close: 17 * 60 + 35, run: 'europe' },
  fr: { timezone: 'Europe/Paris', open: 9 * 60, close: 17 * 60 + 35, run: 'europe' },
  nl: { timezone: 'Europe/Amsterdam', open: 9 * 60, close: 17 * 60 + 35, run: 'europe' },
  uk: { timezone: 'Europe/London', open: 8 * 60, close: 16 * 60 + 35, run: 'europe' },
}

/** The nightly runs (backend `refresh_runs`): time of day in their own zone. */
const RUNS: Record<Session['run'], { timezone: string; minutes: number }> = {
  europe: { timezone: 'Europe/Warsaw', minutes: 18 * 60 },
  us: { timezone: 'America/New_York', minutes: 17 * 60 + 15 },
}

/** The zone the app shows times in. */
const DISPLAY_TIMEZONE = 'Europe/Warsaw'

interface ZonedParts {
  year: number
  month: number
  day: number
  /** Minutes after local midnight. */
  minutes: number
  /** 0 = Sunday … 6 = Saturday. */
  weekday: number
}

function zonedParts(instant: Date, timezone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hourCycle: 'h23',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
  }).formatToParts(instant)
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0)
  const year = get('year')
  const month = get('month')
  const day = get('day')
  return {
    year,
    month,
    day,
    minutes: get('hour') * 60 + get('minute'),
    weekday: new Date(Date.UTC(year, month - 1, day)).getUTCDay(),
  }
}

/** How far a zone's wall clock is ahead of UTC at an instant, in minutes. */
function offsetMinutes(instant: Date, timezone: string): number {
  const p = zonedParts(instant, timezone)
  const wall = Date.UTC(p.year, p.month - 1, p.day, 0, p.minutes)
  return Math.round((wall - Math.floor(instant.getTime() / 60_000) * 60_000) / 60_000)
}

/** The instant a wall-clock time in a zone happens. */
function zonedInstant(
  year: number,
  month: number,
  day: number,
  minutes: number,
  timezone: string,
): Date {
  const naive = Date.UTC(year, month - 1, day, 0, minutes)
  let instant = naive - offsetMinutes(new Date(naive), timezone) * 60_000
  // Near a daylight-saving change the first guess can sit on the other side.
  const corrected = naive - offsetMinutes(new Date(instant), timezone) * 60_000
  if (corrected !== instant) instant = corrected
  return new Date(instant)
}

function session(market: string): Session {
  return SESSIONS[market] ?? SESSIONS[GPW_MARKET]
}

/** True while the market's session is running (Mon–Fri, local hours). */
export function isMarketOpen(market: string, now: Date = new Date()): boolean {
  const s = session(market)
  const p = zonedParts(now, s.timezone)
  const weekday = p.weekday >= 1 && p.weekday <= 5
  return weekday && p.minutes >= s.open && p.minutes < s.close
}

const pad = (n: number) => String(n).padStart(2, '0')

/**
 * When the market's data was last refreshed on schedule, as
 * "YYYY-MM-DD HH:MM" in Warsaw time — the latest weekday run at or before now.
 */
export function lastSyncLabel(market: string, now: Date = new Date()): string {
  const run = RUNS[session(market).run]
  const local = zonedParts(now, run.timezone)
  // Walk back from today (in the run's own zone) to the latest weekday whose
  // run time has passed.
  let cursor = new Date(Date.UTC(local.year, local.month - 1, local.day))
  const ranToday = local.minutes >= run.minutes
  if (!ranToday) cursor = new Date(cursor.getTime() - 86_400_000)
  while (cursor.getUTCDay() === 0 || cursor.getUTCDay() === 6) {
    cursor = new Date(cursor.getTime() - 86_400_000)
  }
  const instant = zonedInstant(
    cursor.getUTCFullYear(),
    cursor.getUTCMonth() + 1,
    cursor.getUTCDate(),
    run.minutes,
    run.timezone,
  )
  const shown = zonedParts(instant, DISPLAY_TIMEZONE)
  return (
    `${shown.year}-${pad(shown.month)}-${pad(shown.day)} ` +
    `${pad(Math.floor(shown.minutes / 60))}:${pad(shown.minutes % 60)}`
  )
}
