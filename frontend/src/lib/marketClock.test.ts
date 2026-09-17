// Trading hours and the last scheduled refresh per market, on each
// exchange's own clock (including the weeks when US and EU daylight saving
// disagree).

import { describe, expect, it } from 'vitest'
import { isMarketOpen, lastSyncLabel } from './marketClock'

/** A UTC instant. */
const at = (iso: string) => new Date(iso)

describe('isMarketOpen', () => {
  it('follows the GPW session on Warsaw time', () => {
    // 16 Sep 2026 (Wednesday): Warsaw is UTC+2.
    expect(isMarketOpen('gpw', at('2026-09-16T06:59:00Z'))).toBe(false) // 08:59
    expect(isMarketOpen('gpw', at('2026-09-16T07:00:00Z'))).toBe(true) // 09:00
    expect(isMarketOpen('gpw', at('2026-09-16T15:04:00Z'))).toBe(true) // 17:04
    expect(isMarketOpen('gpw', at('2026-09-16T15:05:00Z'))).toBe(false) // 17:05
  })

  it('follows New York hours for the US', () => {
    // 17:39 Warsaw = 11:39 New York — the US is trading, the GPW is not.
    const moment = at('2026-09-16T15:39:00Z')
    expect(isMarketOpen('us', moment)).toBe(true)
    expect(isMarketOpen('gpw', moment)).toBe(false)
    expect(isMarketOpen('us', at('2026-09-16T13:29:00Z'))).toBe(false) // 09:29 NY
  })

  it('is closed at the weekend', () => {
    expect(isMarketOpen('uk', at('2026-09-19T10:00:00Z'))).toBe(false) // Saturday
  })

  it('treats an unknown market as the GPW', () => {
    const moment = at('2026-09-16T08:00:00Z')
    expect(isMarketOpen('xx', moment)).toBe(isMarketOpen('gpw', moment))
  })
})

describe('lastSyncLabel', () => {
  it('names the European run in Warsaw time', () => {
    // 20:00 Warsaw on Wednesday: today's 18:00 run has happened.
    expect(lastSyncLabel('gpw', at('2026-09-16T18:00:00Z'))).toBe('2026-09-16 18:00')
    // 10:00 Warsaw: still yesterday's.
    expect(lastSyncLabel('de', at('2026-09-16T08:00:00Z'))).toBe('2026-09-15 18:00')
  })

  it('shows the US run, scheduled in New York time, as Warsaw time', () => {
    // 20:00 Warsaw = 14:00 New York: the latest US run was Tuesday's.
    expect(lastSyncLabel('us', at('2026-09-16T18:00:00Z'))).toBe('2026-09-15 23:15')
  })

  it('keeps the US run right while daylight saving disagrees', () => {
    // 10 March 2026: New York already on summer time, Warsaw not — 17:15 in
    // New York is 22:15 in Warsaw that week.
    expect(lastSyncLabel('us', at('2026-03-11T12:00:00Z'))).toBe('2026-03-10 22:15')
  })

  it('skips the weekend', () => {
    // Monday 10:00 Warsaw → Friday's run.
    expect(lastSyncLabel('gpw', at('2026-09-14T08:00:00Z'))).toBe('2026-09-11 18:00')
    // Monday 03:00 Warsaw is still Sunday in New York → Friday's US run.
    expect(lastSyncLabel('us', at('2026-09-14T01:00:00Z'))).toBe('2026-09-11 23:15')
  })
})
