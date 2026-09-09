// Bar-time conversion for the candlestick chart. Lives here rather than in
// StockChart.tsx because a module that exports both a component and a plain
// function cannot be hot-swapped by Vite's Fast Refresh (react-refresh's
// only-export-components rule).

import type { Time } from 'lightweight-charts'

/** Matches the trailing UTC offset of an ISO timestamp: "+02:00", "-05:00", "Z". */
const ISO_OFFSET = /(?:Z|([+-])(\d{2}):(\d{2}))$/

/**
 * Convert an API bar time into what Lightweight Charts wants.
 *
 * A daily/weekly bar arrives as "2026-09-04" and is handed over unchanged — the
 * library's own business-day format. An intraday bar arrives as a full ISO
 * timestamp ("2026-09-04T13:00:00+02:00") and must become UNIX seconds.
 *
 * The library has no timezone support: it renders every timestamp as UTC. Left
 * alone, a bar that traded at 13:00 in Warsaw would be labelled 11:00, so the
 * exchange's own offset is folded into the number — the standard way to pin the
 * axis to exchange time. Reading the offset off each bar keeps the same chart
 * correct across a daylight-saving change (+01:00 on March bars, +02:00 on
 * September ones).
 */
export function toChartTime(value: string): Time {
  if (!value.includes('T')) return value as Time // business day, as-is
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value as Time
  const m = ISO_OFFSET.exec(value)
  const offsetMinutes =
    m && m[1] ? (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3])) : 0
  return (Math.floor(ms / 1000) + offsetMinutes * 60) as Time
}
