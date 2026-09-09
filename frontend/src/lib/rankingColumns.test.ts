// Unit tests for the shared ranking-column registry — the visibility rules AND
// the column order that the Dashboard, Watchlist and Filters pages all read.

import { describe, it, expect } from 'vitest'
import {
  RANKING_COLUMNS,
  canMoveColumn,
  columnsCustomized,
  initialSortDir,
  isColumnVisible,
  moveColumn,
  normalizeOrder,
  orderCustomized,
  orderedColumns,
  spliceAfter,
  tableMinWidth,
  toggleColumnVisibility,
  visibleColumns,
  type ColumnVisibility,
  type RankingColumnId,
  type RenderColumn,
} from './rankingColumns'

/** A stand-in for the dynamic columns the Dashboard builds per trading method. */
function renderCol(key: string): RenderColumn {
  return {
    key,
    label: key,
    sortKey: null,
    align: 'right',
    width: 130,
    cell: () => null,
  }
}

describe('ranking column registry', () => {
  it('has exactly one required (locked) column, and it comes first', () => {
    const required = RANKING_COLUMNS.filter((c) => c.required)
    expect(required.map((c) => c.id)).toEqual(['company'])
    expect(RANKING_COLUMNS[0].id).toBe('company')
  })

  it('gives every column a unique id and a sane width', () => {
    const ids = RANKING_COLUMNS.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const col of RANKING_COLUMNS) expect(col.width).toBeGreaterThan(0)
  })

  it('falls back to each column default when nothing is stored', () => {
    const shown = visibleColumns({}).map((c) => c.id)
    expect(shown).toEqual(
      RANKING_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.id),
    )
    expect(columnsCustomized({})).toBe(false)
  })

  it('keeps the visible columns in registry (table) order', () => {
    const stored: ColumnVisibility = { volume: true, sector: true }
    const shown = visibleColumns(stored).map((c) => c.id)
    const order = RANKING_COLUMNS.map((c) => c.id)
    const positions = shown.map((id) => order.indexOf(id))
    expect(positions).toEqual([...positions].sort((a, b) => a - b))
  })

  it('toggles a column and reports the selection as customized', () => {
    const off = toggleColumnVisibility({}, 'signal') // on by default → off
    expect(off.signal).toBe(false)
    expect(columnsCustomized(off)).toBe(true)
    expect(visibleColumns(off).map((c) => c.id)).not.toContain('signal')

    const backOn = toggleColumnVisibility(off, 'signal')
    expect(backOn.signal).toBe(true)
    // Explicitly re-ticking a default-on column is not a customization.
    expect(columnsCustomized(backOn)).toBe(false)
  })

  it('never lets the locked identity column be hidden', () => {
    const attempted = toggleColumnVisibility({}, 'company')
    expect(attempted.company).toBeUndefined()
    const company = RANKING_COLUMNS[0]
    expect(isColumnVisible(company, { company: false })).toBe(true)
    // Even with everything else off, the table still has a column.
    const allOff: ColumnVisibility = Object.fromEntries(
      RANKING_COLUMNS.map((c) => [c.id, false]),
    )
    expect(visibleColumns(allOff).map((c) => c.id)).toEqual(['company'])
  })

  it('sums the table min-width from the visible columns plus any extra', () => {
    const cols = [renderCol('a'), renderCol('b')]
    expect(tableMinWidth(cols)).toBe(260)
    expect(tableMinWidth(cols, 60)).toBe(320)
  })

  it('sorts text columns ascending first and metrics descending first', () => {
    expect(initialSortDir('ticker')).toBe('asc')
    expect(initialSortDir('name')).toBe('asc')
    expect(initialSortDir('sector')).toBe('asc')
    expect(initialSortDir('currentRating')).toBe('desc')
    expect(initialSortDir('lastPrice')).toBe('desc')
    // Not a registry column (the Dashboard's combined score) — metrics rule.
    expect(initialSortDir('combinedScore')).toBe('desc')
  })
})

describe('spliceAfter', () => {
  const base = [renderCol('company'), renderCol('signal'), renderCol('daysSinceSignal')]

  it('inserts the extra columns directly after the anchor', () => {
    const out = spliceAfter(base, 'signal', [renderCol('vsa'), renderCol('combined')])
    expect(out.map((c) => c.key)).toEqual([
      'company',
      'signal',
      'vsa',
      'combined',
      'daysSinceSignal',
    ])
  })

  it('appends when the anchor column is hidden', () => {
    const withoutSignal = [renderCol('company'), renderCol('daysSinceSignal')]
    const out = spliceAfter(withoutSignal, 'signal', [renderCol('combined')])
    expect(out.map((c) => c.key)).toEqual(['company', 'daysSinceSignal', 'combined'])
  })

  it('returns the original list when there is nothing to splice', () => {
    expect(spliceAfter(base, 'signal', [])).toBe(base)
  })
})

describe('column order', () => {
  const registryOrder = RANKING_COLUMNS.map((c) => c.id)

  it('falls back to registry order when nothing is stored', () => {
    expect(normalizeOrder(null)).toEqual(registryOrder)
    expect(normalizeOrder([])).toEqual(registryOrder)
    expect(orderCustomized([])).toBe(false)
    expect(orderedColumns([]).map((c) => c.id)).toEqual(registryOrder)
  })

  it('completes a partial stored order with the columns it never mentioned', () => {
    const stored: RankingColumnId[] = ['volume', 'signal']
    const out = normalizeOrder(stored)
    // The stored ids lead (after the pinned one); nothing is lost or duplicated.
    expect(out.slice(0, 3)).toEqual(['company', 'volume', 'signal'])
    expect(new Set(out)).toEqual(new Set(registryOrder))
    expect(out).toHaveLength(registryOrder.length)
  })

  it('drops ids the app no longer has, and duplicates', () => {
    const stored = ['gone', 'volume', 'volume'] as unknown as RankingColumnId[]
    const out = normalizeOrder(stored)
    expect(out).not.toContain('gone')
    expect(out).toHaveLength(registryOrder.length)
    expect(out.filter((id) => id === 'volume')).toHaveLength(1)
  })

  it('pins the locked identity column first however it was stored', () => {
    const out = normalizeOrder(['rating', 'company', 'signal'])
    expect(out[0]).toBe('company')
    expect(out.slice(1, 3)).toEqual(['rating', 'signal'])
  })

  it('moves a column one place in either direction', () => {
    const moved = moveColumn([], 'signal', -1)
    const before = registryOrder.indexOf('signal')
    expect(moved.indexOf('signal')).toBe(before - 1)
    expect(orderCustomized(moved)).toBe(true)

    // Moving it back lands on the registry order again.
    expect(moveColumn(moved, 'signal', 1)).toEqual(registryOrder)
    expect(orderCustomized(moveColumn(moved, 'signal', 1))).toBe(false)
  })

  it('refuses to move past either end, or past the pinned column', () => {
    const last = registryOrder[registryOrder.length - 1]
    expect(moveColumn([], last, 1)).toEqual(registryOrder)
    // 'name' sits directly after the pinned identity column.
    expect(moveColumn([], 'name', -1)).toEqual(registryOrder)
    // The pinned column itself never moves.
    expect(moveColumn([], 'company', 1)).toEqual(registryOrder)
  })

  it('renders the visible columns in the user order, not the registry one', () => {
    // Put the signal in front of the price, then show only those three.
    let order = normalizeOrder([])
    for (let i = 0; i < 7; i += 1) order = moveColumn(order, 'signal', -1)
    const stored: ColumnVisibility = {
      priceChangePct: false,
      rating: false,
      daysSinceSignal: false,
    }
    const shown = visibleColumns(stored, order).map((c) => c.id)
    expect(shown).toEqual(['company', 'signal', 'lastPrice'])
    // Without the order argument the registry arrangement still applies.
    expect(visibleColumns(stored).map((c) => c.id)).toEqual([
      'company',
      'lastPrice',
      'signal',
    ])
  })
})

describe('moving a shown column past hidden ones', () => {
  // Most columns are off by default, so stepping one raw slot at a time would
  // often move a column behind a hidden neighbour and leave the table looking
  // unchanged. With a visibility map, a shown column hops to its nearest shown
  // neighbour instead.
  const shownByDefault: ColumnVisibility = {}

  it('lands next to the nearest visible neighbour', () => {
    const moved = moveColumn([], 'rating', -1, shownByDefault)
    expect(visibleColumns(shownByDefault, moved).map((c) => c.id)).toEqual([
      'company',
      'lastPrice',
      'rating',
      'priceChangePct',
      'signal',
      'daysSinceSignal',
    ])
    // The hidden 52-week columns it hopped over are still in the order.
    expect(new Set(moved)).toEqual(new Set(RANKING_COLUMNS.map((c) => c.id)))
  })

  it('still steps one slot at a time for a hidden column', () => {
    const moved = moveColumn([], 'volume', -1, shownByDefault)
    const before = RANKING_COLUMNS.map((c) => c.id).indexOf('volume')
    expect(moved.indexOf('volume')).toBe(before - 1)
  })

  it('reports when a move would do nothing', () => {
    // 'lastPrice' is the first shown column after the pinned one.
    expect(canMoveColumn([], 'lastPrice', -1, shownByDefault)).toBe(false)
    expect(canMoveColumn([], 'lastPrice', 1, shownByDefault)).toBe(true)
    // The pinned column never moves, in either direction.
    expect(canMoveColumn([], 'company', 1, shownByDefault)).toBe(false)
    // Last shown column: nothing visible to its right.
    expect(canMoveColumn([], 'daysSinceSignal', 1, shownByDefault)).toBe(false)
  })
})
