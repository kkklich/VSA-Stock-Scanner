// The pooled list's self-report: are all these rows from the same session?
//
// The case that matters is the evening window. Europe settles in the late
// Warsaw afternoon, the US at ~22:15 Warsaw time, so between roughly 18:00 and
// 23:15 a pooled list carries today's European rows beside yesterday's
// American ones — and the Dashboard opens on "biggest movers", which then
// compares two different days. The data is right; only the silence was wrong.

import { describe, expect, it } from 'vitest'
import { sessionMismatch, sessionsOf } from './sessions'

const row = (lastSession?: string | null) => ({ lastSession })

describe('sessionsOf', () => {
  it('lists the distinct sessions newest first', () => {
    expect(
      sessionsOf([row('2026-09-16'), row('2026-09-17'), row('2026-09-16')]),
    ).toEqual(['2026-09-17', '2026-09-16'])
  })

  it('ignores rows that do not say (an older backend)', () => {
    expect(sessionsOf([row(undefined), row(null), row('2026-09-17')])).toEqual([
      '2026-09-17',
    ])
  })
})

describe('sessionMismatch', () => {
  it('says nothing when every row is from the same session', () => {
    expect(sessionMismatch([row('2026-09-17'), row('2026-09-17')])).toBeNull()
  })

  it('says nothing when no row carries a session at all', () => {
    expect(sessionMismatch([row(undefined), row(null)])).toBeNull()
  })

  it('counts the rows behind the newest session', () => {
    // Three European rows on today's session, two American ones still on
    // yesterday's because the US has not closed yet.
    const rows = [
      row('2026-09-17'),
      row('2026-09-17'),
      row('2026-09-17'),
      row('2026-09-16'),
      row('2026-09-16'),
    ]
    expect(sessionMismatch(rows)).toEqual({
      newest: '2026-09-17',
      oldest: '2026-09-16',
      behind: 2,
    })
  })

  it('reports the full span when more than two sessions are mixed', () => {
    const rows = [row('2026-09-17'), row('2026-09-16'), row('2026-09-11')]
    expect(sessionMismatch(rows)).toEqual({
      newest: '2026-09-17',
      oldest: '2026-09-11',
      behind: 2,
    })
  })

  it('does not count a silent row as behind', () => {
    // A row from an older backend says nothing; claiming it lags would be a
    // guess, and the count is meant to be exact.
    const rows = [row('2026-09-17'), row(undefined), row('2026-09-16')]
    expect(sessionMismatch(rows)?.behind).toBe(1)
  })
})
