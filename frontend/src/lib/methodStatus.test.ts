import { describe, expect, it } from 'vitest'
import { CLASSIC_VSA_ENABLED, isMethodActive } from './methodStatus'
import { orderedColumns, visibleColumns } from './rankingColumns'

describe('inactive VSA methods in the live UI', () => {
  it('keeps V4 and the other active methods while archiving Classic, V1 and V3', () => {
    expect(CLASSIC_VSA_ENABLED).toBe(false)
    for (const id of ['vsa', 'glinicki', 'vsa3']) expect(isMethodActive(id)).toBe(false)
    for (const id of ['vsa4', 'minervini', 'breakout', 'weinstein', 'pocket_pivot']) {
      expect(isMethodActive(id)).toBe(true)
    }
  })

  it('does not restore classic columns from old browser preferences or the picker', () => {
    const old = { rating: true, ratingChange: true, signal: true,
      daysSinceSignal: true, aiConfidence: true, trend: true }
    const archived = new Set(Object.keys(old))
    expect(visibleColumns(old).some((c) => archived.has(c.id))).toBe(false)
    expect(orderedColumns(['rating', 'signal']).some((c) => archived.has(c.id))).toBe(false)
    expect(visibleColumns(old).some((c) => c.id === 'lastPrice')).toBe(true)
  })
})
