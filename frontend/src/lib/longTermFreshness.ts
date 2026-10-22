import type { LongTermItem } from '../types/longTerm'

type FreshnessItem = Pick<LongTermItem, 'fundamentalsObservedAt' | 'asOf' | 'missing'>

export interface LongTermFreshness {
  oldestFinancialObservation: string | null
  newestFinancialObservation: string | null
  missingFinancialCount: number
  staleFinancialCount: number
  latestPriceSession: string | null
}

/** Validate a calendar date without applying the viewer's timezone. */
function isSessionDate(value: string | null): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const instant = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(instant) && new Date(instant).toISOString().slice(0, 10) === value
}

function observationTime(value: string | null): number | null {
  // A date alone, or a naive local timestamp, cannot identify acquisition time.
  if (!value || !isSessionDate(value.slice(0, 10)) || !/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) {
    return null
  }
  const instant = Date.parse(value)
  return Number.isFinite(instant) ? instant : null
}

/** Summarise stored timestamps; the backend owns the financial-staleness rule. */
export function summarizeLongTermFreshness(items: readonly FreshnessItem[]): LongTermFreshness {
  let oldest: number | null = null
  let newest: number | null = null
  let missingFinancialCount = 0
  let staleFinancialCount = 0
  let latestPriceSession: string | null = null

  for (const item of items) {
    const observed = observationTime(item.fundamentalsObservedAt)
    if (observed !== null) {
      oldest = oldest === null ? observed : Math.min(oldest, observed)
      newest = newest === null ? observed : Math.max(newest, observed)
    }
    if (observed === null || item.missing.includes('fundamentals_missing')) missingFinancialCount += 1
    if (item.missing.includes('fundamentals_stale')) staleFinancialCount += 1
    if (isSessionDate(item.asOf) && (latestPriceSession === null || item.asOf > latestPriceSession)) {
      latestPriceSession = item.asOf
    }
  }

  return {
    oldestFinancialObservation: oldest === null ? null : new Date(oldest).toISOString(),
    newestFinancialObservation: newest === null ? null : new Date(newest).toISOString(),
    missingFinancialCount,
    staleFinancialCount,
    latestPriceSession,
  }
}
