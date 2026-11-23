import { useCallback, useMemo, useState, type SetStateAction } from 'react'
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
  /** The effective sort, including the opening order before any selection. */
  sort: SortLevel<K>[]
  onHeaderSort: (col: K, shiftKey: boolean) => void
  /** Menu pick. `additive` appends a tie-breaker. */
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
  initial: SortLevel<K> | null,
  /** Direction a column starts in — labels ascend, numbers descend. */
  initialDir: InitialDir<K>,
  /** Called after any change; the paginated pages use it to go back to page 1. */
  onChange?: () => void,
  controlled?: readonly [SortLevel<K>[], (action: SetStateAction<SortLevel<K>[]>) => void],
): TableSort<K> {
  const local = useState<SortLevel<K>[]>([])
  const [selected, setSort] = controlled ?? local
  const initialKey = initial?.key
  const initialDirection = initial?.dir
  const fallback = useMemo<SortLevel<K>[]>(() => initialKey !== undefined && initialDirection !== undefined
    ? [{ key: initialKey, dir: initialDirection }] : [], [initialKey, initialDirection])
  const sort = selected.length ? selected : fallback

  const onHeaderSort = useCallback((col: K, shiftKey: boolean) => {
    setSort((levels) => {
      const effective = levels.length ? levels : fallback
      const active = effective.find(({ key }) => key === col)
      if (!shiftKey && active) return setLevelDir(effective, col, active.dir === 'asc' ? 'desc' : 'asc')
      return applySortClick(effective, col, { additive: shiftKey || levels.length > 0, initialDir })
    })
    onChange?.()
  }, [fallback, initialDir, onChange, setSort])

  const onSort = useCallback(
    (col: K, additive = false) => {
      setSort((levels) => applySortClick(levels.length ? levels : fallback, col, { additive, initialDir }))
      onChange?.()
    },
    [fallback, initialDir, onChange, setSort],
  )

  const onSortDirChange = useCallback(
    (col: K, dir: SortDir) => {
      setSort((levels) => setLevelDir(levels.length ? levels : fallback, col, dir))
      onChange?.()
    },
    [fallback, onChange, setSort],
  )

  const onRemoveLevel = useCallback(
    (col: K) => {
      setSort((levels) => removeLevel(levels, col))
      onChange?.()
    },
    [onChange, setSort],
  )

  const key = useMemo(() => sortKey(sort), [sort])

  return { sort, onHeaderSort, onSort, onSortDirChange, onRemoveLevel, key }
}
