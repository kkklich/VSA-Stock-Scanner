// The sort state every list page holds: an ordered list of sort levels plus
// the three handlers the table headers and the phone Sort menu drive it with.
//
// Five pages (Dashboard, Watchlist, Filters, Volume surge, Capex) each used to
// keep a `sortBy` + `sortDir` pair and re-implement the same click handler.
// They now share this, so "sort by one column, then by another" behaves the
// same everywhere and the rules live in one place (`lib/sorting.ts`).

import { useCallback, useMemo, useState } from 'react'
import {
  applySortClick,
  removeLevel,
  setLevelDir,
  sortKey,
  type InitialDir,
  type SortDir,
  type SortLevel,
} from '../lib/sorting'

export interface TableSort<K extends string> {
  /** The whole sort, outermost level first. Never empty. */
  sort: SortLevel<K>[]
  /** Header click / menu pick. `additive` = shift-click, i.e. "then by". */
  onSort: (col: K, additive?: boolean) => void
  /** Set one level's direction (the menu's explicit ↑ / ↓ buttons). */
  onSortDirChange: (col: K, dir: SortDir) => void
  /** Drop one level (a no-op on the last remaining one). */
  onRemoveLevel: (col: K) => void
  /** Stable string for effect dependencies — the levels are objects. */
  key: string
}

export function useTableSort<K extends string>(
  /** The page's opening order, e.g. `{ key: 'currentRating', dir: 'desc' }`. */
  initial: SortLevel<K>,
  /** Direction a column starts in — labels ascend, numbers descend. */
  initialDir: InitialDir<K>,
  /** Called after any change; the paginated pages use it to go back to page 1. */
  onChange?: () => void,
): TableSort<K> {
  const [sort, setSort] = useState<SortLevel<K>[]>([initial])

  const onSort = useCallback(
    (col: K, additive = false) => {
      setSort((levels) => applySortClick(levels, col, { additive, initialDir }))
      onChange?.()
    },
    [initialDir, onChange],
  )

  const onSortDirChange = useCallback(
    (col: K, dir: SortDir) => {
      setSort((levels) => setLevelDir(levels, col, dir))
      onChange?.()
    },
    [onChange],
  )

  const onRemoveLevel = useCallback(
    (col: K) => {
      setSort((levels) => removeLevel(levels, col))
      onChange?.()
    },
    [onChange],
  )

  const key = useMemo(() => sortKey(sort), [sort])

  return { sort, onSort, onSortDirChange, onRemoveLevel, key }
}
