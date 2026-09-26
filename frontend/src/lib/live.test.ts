// What the pages say about today's live prices: which markets are live, as of
// when, and from which finished session the analysis comes.

import { describe, expect, it } from 'vitest'
import type { ApiLivePrice } from '../api/stocksApi'
import { fmtLiveTime, fmtSessionDay, liveSummary, notTradedYet } from './live'

function live(asOf: string, overrides: Partial<ApiLivePrice> = {}): ApiLivePrice {
  return {
    sessionDate: '2026-09-25',
    price: 110,
    open: 101,
    high: 111,
    low: 100,
    volume: 90_000,
    previousClose: 100,
    changePct: 10,
    asOf,
    fetchedAt: asOf,
    ...overrides,
  }
}

describe('liveSummary', () => {
  it('is null when no row carries a live price', () => {
    expect(liveSummary([])).toBeNull()
    expect(liveSummary([{ market: 'gpw', lastSession: '2026-09-24', live: null }])).toBeNull()
    // An older backend sends no `live` at all.
    expect(liveSummary([{ market: 'gpw', lastSession: '2026-09-24' }])).toBeNull()
  })

  it('keeps the newest trade time per market, in the app market order', () => {
    const summary = liveSummary([
      { market: 'us', lastSession: '2026-09-24', live: live('2026-09-25T17:30:00Z') },
      { market: 'gpw', lastSession: '2026-09-24', live: live('2026-09-25T11:44:00Z') },
      { market: 'gpw', lastSession: '2026-09-24', live: live('2026-09-25T11:59:00Z') },
      // A row without a live price does not take part.
      { market: 'de', lastSession: '2026-09-24', live: null },
    ])
    expect(summary).not.toBeNull()
    expect(summary?.markets).toEqual([
      { market: 'gpw', asOf: '2026-09-25T11:59:00Z' },
      { market: 'us', asOf: '2026-09-25T17:30:00Z' },
    ])
    expect(summary?.finishedSession).toBe('2026-09-24')
  })

  it('treats a row without a market as the GPW', () => {
    const summary = liveSummary([{ live: live('2026-09-25T11:00:00Z') }])
    expect(summary?.markets).toEqual([{ market: 'gpw', asOf: '2026-09-25T11:00:00Z' }])
    expect(summary?.finishedSession).toBeNull()
  })
})

describe('fmtLiveTime', () => {
  it('is the time alone on the same day', () => {
    const traded = new Date(2026, 8, 25, 13, 44)
    expect(fmtLiveTime(traded.toISOString(), new Date(2026, 8, 25, 14, 5))).toBe('13:44')
  })

  it('names the day when the trade was on another one', () => {
    const traded = new Date(2026, 8, 24, 17, 4)
    expect(fmtLiveTime(traded.toISOString(), new Date(2026, 8, 25, 10, 0))).toBe(
      '24.09 17:04',
    )
  })

  it('shows a dash for nonsense', () => {
    expect(fmtLiveTime('not a time')).toBe('—')
  })
})

describe('fmtSessionDay', () => {
  it('reads a session date the way the notes name days', () => {
    expect(fmtSessionDay('2026-09-24')).toBe('24.09')
  })
})

describe('notTradedYet', () => {
  it('is a live price with no volume yet', () => {
    expect(notTradedYet(live('2026-09-25T08:00:00Z', { volume: 0 }))).toBe(true)
    expect(notTradedYet(live('2026-09-25T08:00:00Z'))).toBe(false)
    // Unknown volume is not "no trade".
    expect(notTradedYet(live('2026-09-25T08:00:00Z', { volume: null }))).toBe(false)
  })
})
