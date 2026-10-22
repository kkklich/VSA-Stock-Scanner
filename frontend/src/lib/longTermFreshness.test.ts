import { describe, expect, it } from 'vitest'
import { summarizeLongTermFreshness } from './longTermFreshness'

function item(fundamentalsObservedAt: string | null, asOf: string | null, missing: string[] = []) {
  return { fundamentalsObservedAt, asOf, missing }
}

describe('summarizeLongTermFreshness', () => {
  it('keeps empty or unknown observations explicit', () => {
    expect(summarizeLongTermFreshness([])).toEqual({
      oldestFinancialObservation: null, newestFinancialObservation: null,
      missingFinancialCount: 0, staleFinancialCount: 0, latestPriceSession: null,
    })
    expect(summarizeLongTermFreshness([item(null, null)])).toEqual({
      oldestFinancialObservation: null, newestFinancialObservation: null,
      missingFinancialCount: 1, staleFinancialCount: 0, latestPriceSession: null,
    })
  })

  it('orders acquisition instants correctly across timezone offsets and keeps sessions as dates', () => {
    expect(summarizeLongTermFreshness([
      item('2026-10-22T00:30:00+02:00', '2026-10-21'),
      item('2026-10-21T23:00:00-04:00', '2026-10-22'),
      item('2026-10-21T22:30:00Z', '2026-10-20'),
    ])).toEqual({
      oldestFinancialObservation: '2026-10-21T22:30:00.000Z',
      newestFinancialObservation: '2026-10-22T03:00:00.000Z',
      missingFinancialCount: 0, staleFinancialCount: 0, latestPriceSession: '2026-10-22',
    })
  })

  it('counts backend flags per company, without inventing a client-side staleness threshold', () => {
    const result = summarizeLongTermFreshness([
      item('2000-01-01T12:00:00Z', '2026-10-22'),
      item('2026-10-21T12:00:00Z', '2026-10-22', ['fundamentals_stale', 'fundamentals_stale']),
      item('2026-10-20T12:00:00Z', null, ['fundamentals_missing']),
      item(null, null, ['fundamentals_missing']),
    ])
    expect(result.missingFinancialCount).toBe(2)
    expect(result.staleFinancialCount).toBe(1)
  })

  it.each(['invalid', '2026-02-30T12:00:00Z', '2026-10-22', '2026-10-22T12:00:00'])(
    'treats ambiguous or invalid acquisition time %s as missing', (value) => {
      const result = summarizeLongTermFreshness([item(value, '2026-02-30')])
      expect(result.oldestFinancialObservation).toBeNull()
      expect(result.newestFinancialObservation).toBeNull()
      expect(result.missingFinancialCount).toBe(1)
      expect(result.latestPriceSession).toBeNull()
    },
  )

  it('accepts leap-day sessions and rejects timestamps in the session-date field', () => {
    const result = summarizeLongTermFreshness([
      item(null, '2024-02-29'), item(null, '2026-10-22T00:00:00Z'), item(null, '2026-13-01'),
    ])
    expect(result.latestPriceSession).toBe('2024-02-29')
  })
})
