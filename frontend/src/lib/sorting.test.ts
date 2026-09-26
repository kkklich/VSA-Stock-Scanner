// The rules behind "sort by one column, then by another" — shared by every
// table header, the phone Sort menu and all five list pages.

import { describe, expect, it } from 'vitest'
import {
  MAX_SORT_LEVELS,
  addLevel,
  applySortClick,
  normalizeSort,
  removeLevel,
  serializeSort,
  setLevelDir,
  sortKey,
  type SortLevel,
} from './sorting'

type Key = 'sector' | 'currentRating' | 'lastPrice' | 'ticker' | 'volume'

/** Labels ascend, numbers descend — the app's own convention. */
const initialDir = (key: Key) => (key === 'sector' || key === 'ticker' ? 'asc' : 'desc')

const RATING: SortLevel<Key>[] = [{ key: 'currentRating', dir: 'desc' }]

describe('applySortClick — plain click', () => {
  it('sorts by a new column in its natural direction', () => {
    expect(applySortClick(RATING, 'sector', { initialDir })).toEqual([
      { key: 'sector', dir: 'asc' },
    ])
    expect(applySortClick(RATING, 'lastPrice', { initialDir })).toEqual([
      { key: 'lastPrice', dir: 'desc' },
    ])
  })

  it('flips the direction when the column is already the only sort', () => {
    expect(applySortClick(RATING, 'currentRating', { initialDir })).toEqual([
      { key: 'currentRating', dir: 'asc' },
    ])
  })

  it('collapses a multi-level sort back to the clicked column', () => {
    // The reliable way back to a simple, obvious ordering.
    const deep: SortLevel<Key>[] = [
      { key: 'sector', dir: 'asc' },
      { key: 'currentRating', dir: 'desc' },
    ]
    expect(applySortClick(deep, 'currentRating', { initialDir })).toEqual([
      { key: 'currentRating', dir: 'desc' },
    ])
  })
})

describe('applySortClick — shift-click (additive)', () => {
  it('appends an unsorted column as the next level', () => {
    expect(
      applySortClick(RATING, 'sector', { additive: true, initialDir }),
    ).toEqual([
      { key: 'currentRating', dir: 'desc' },
      { key: 'sector', dir: 'asc' },
    ])
  })

  it('flips an existing level in place, keeping its position', () => {
    const two: SortLevel<Key>[] = [
      { key: 'sector', dir: 'asc' },
      { key: 'currentRating', dir: 'desc' },
    ]
    expect(applySortClick(two, 'sector', { additive: true, initialDir })).toEqual([
      { key: 'sector', dir: 'desc' },
      { key: 'currentRating', dir: 'desc' },
    ])
  })

  it('removes a level on the click after its flip (the full cycle)', () => {
    const flipped: SortLevel<Key>[] = [
      { key: 'currentRating', dir: 'desc' },
      { key: 'sector', dir: 'desc' }, // already flipped off 'asc'
    ]
    expect(applySortClick(flipped, 'sector', { additive: true, initialDir })).toEqual(
      RATING,
    )
  })

  it('never empties the sort — the last level cycles instead of vanishing', () => {
    const flipped: SortLevel<Key>[] = [{ key: 'currentRating', dir: 'asc' }]
    expect(
      applySortClick(flipped, 'currentRating', { additive: true, initialDir }),
    ).toEqual(RATING)
  })

  it('replaces the deepest level once the cap is reached', () => {
    // Doing nothing on a click would read as a bug, so the deepest tie-break
    // gives way instead.
    const full: SortLevel<Key>[] = [
      { key: 'sector', dir: 'asc' },
      { key: 'currentRating', dir: 'desc' },
      { key: 'lastPrice', dir: 'desc' },
    ]
    expect(full).toHaveLength(MAX_SORT_LEVELS)
    expect(applySortClick(full, 'volume', { additive: true, initialDir })).toEqual([
      { key: 'sector', dir: 'asc' },
      { key: 'currentRating', dir: 'desc' },
      { key: 'volume', dir: 'desc' },
    ])
  })

  it('addLevel is the same gesture', () => {
    expect(addLevel(RATING, 'ticker', initialDir)).toEqual([
      { key: 'currentRating', dir: 'desc' },
      { key: 'ticker', dir: 'asc' },
    ])
  })
})

describe('setLevelDir / removeLevel', () => {
  const two: SortLevel<Key>[] = [
    { key: 'sector', dir: 'asc' },
    { key: 'currentRating', dir: 'desc' },
  ]

  it('sets one level’s direction and leaves the others alone', () => {
    expect(setLevelDir(two, 'currentRating', 'asc')).toEqual([
      { key: 'sector', dir: 'asc' },
      { key: 'currentRating', dir: 'asc' },
    ])
  })

  it('drops a level', () => {
    expect(removeLevel(two, 'sector')).toEqual([{ key: 'currentRating', dir: 'desc' }])
  })

  it('keeps the last remaining level — a table is always ordered', () => {
    expect(removeLevel(RATING, 'currentRating')).toEqual(RATING)
  })
})

describe('serializeSort', () => {
  it('sends one level exactly as the app always did', () => {
    expect(serializeSort(RATING)).toEqual({
      sortBy: 'currentRating',
      sortDir: 'desc',
    })
  })

  it('sends several levels as paired comma-separated lists', () => {
    expect(
      serializeSort<Key>([
        { key: 'sector', dir: 'asc' },
        { key: 'currentRating', dir: 'desc' },
      ]),
    ).toEqual({ sortBy: 'sector,currentRating', sortDir: 'asc,desc' })
  })

  it('is null when there is nothing to sort by', () => {
    expect(serializeSort<Key>([])).toBeNull()
  })
})

describe('sortKey', () => {
  it('changes only when the ordering does', () => {
    const a: SortLevel<Key>[] = [{ key: 'sector', dir: 'asc' }]
    const b: SortLevel<Key>[] = [{ key: 'sector', dir: 'asc' }]
    expect(sortKey(a)).toBe(sortKey(b))
    expect(sortKey(a)).not.toBe(sortKey(setLevelDir(a, 'sector', 'desc')))
  })
})

describe('normalizeSort', () => {
  const valid = (k: Key) => k !== 'volume'
  const fallback: SortLevel<Key> = { key: 'currentRating', dir: 'desc' }

  it('drops columns that no longer exist', () => {
    expect(
      normalizeSort<Key>(
        [
          { key: 'sector', dir: 'asc' },
          { key: 'volume', dir: 'desc' },
        ],
        valid,
        fallback,
      ),
    ).toEqual([{ key: 'sector', dir: 'asc' }])
  })

  it('drops a repeated column and caps the depth', () => {
    expect(
      normalizeSort<Key>(
        [
          { key: 'sector', dir: 'asc' },
          { key: 'sector', dir: 'desc' },
        ],
        valid,
        fallback,
      ),
    ).toEqual([{ key: 'sector', dir: 'asc' }])
  })

  it('falls back rather than leaving the table unordered', () => {
    expect(normalizeSort<Key>([{ key: 'volume', dir: 'desc' }], valid, fallback)).toEqual(
      [fallback],
    )
  })
})
