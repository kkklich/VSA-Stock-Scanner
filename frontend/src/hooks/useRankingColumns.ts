// Shared column selection for the ranking tables.
//
// One hook, three pages (Dashboard, Watchlist, Filters): the user picks which
// columns to show AND what order they sit in, once, and every stock list
// follows — on desktop and on a phone. Pages get the raw visibility map and
// the column order (for the picker) plus the translated render columns (for
// the table and the card list).

import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersistentState } from './usePersistentState'
import {
  RANKING_COLUMNS,
  RANKING_COLUMNS_KEY,
  RANKING_COLUMN_ORDER_KEY,
  columnLabel,
  columnsCustomized,
  moveColumn,
  normalizeOrder,
  orderCustomized,
  toRenderColumns,
  visibleColumns,
  toggleColumnVisibility,
  type ColumnOrder,
  type ColumnVisibility,
  type RankingColumnId,
  type RenderColumn,
} from '../lib/rankingColumns'
import type { TFunction } from 'i18next'
import type { RankingSortKey } from '../api/stocksApi'
import type { SortOption } from '../components/SortMenu'

export function useRankingColumns() {
  const { t } = useTranslation()
  const [stored, setStored] = usePersistentState<ColumnVisibility>(
    RANKING_COLUMNS_KEY,
    {},
  )

  // The user's left → right arrangement, in its own key so an existing
  // visibility selection keeps working untouched.
  const [storedOrder, setStoredOrder] = usePersistentState<ColumnOrder>(
    RANKING_COLUMN_ORDER_KEY,
    [],
  )
  const order = useMemo(() => normalizeOrder(storedOrder), [storedOrder])

  const columns = useMemo(() => visibleColumns(stored, order), [stored, order])
  const renderColumns = useMemo(() => toRenderColumns(columns, t), [columns, t])
  const customized = useMemo(
    () => columnsCustomized(stored) || orderCustomized(order),
    [stored, order],
  )

  const toggle = useCallback(
    (id: RankingColumnId) => setStored((s) => toggleColumnVisibility(s, id)),
    [setStored],
  )
  const move = useCallback(
    (id: RankingColumnId, delta: -1 | 1) =>
      setStoredOrder((o) => moveColumn(o, id, delta, stored)),
    [setStoredOrder, stored],
  )
  // Reset puts back both halves of the choice — which columns and in what order.
  const reset = useCallback(() => {
    setStored({})
    setStoredOrder([])
  }, [setStored, setStoredOrder])

  return {
    /** Raw visibility map — what the ColumnPicker binds to. */
    stored,
    /** Full column order (every column, hidden ones included). */
    order,
    toggle,
    move,
    reset,
    customized,
    /** Translated columns to render, in table order. */
    renderColumns,
    /** How many columns are on (shown as the picker's badge). */
    count: columns.length,
  }
}

/**
 * Sort options for the phone/tablet `SortMenu`, derived from the columns the
 * user actually kept — a card list has no headers to tap, so its sort menu has
 * to offer whatever the table's headers would have. Unsortable columns (the
 * sparkline) drop out.
 *
 * `activeSortBy` is kept in the list even when its column is hidden: hiding a
 * column does not change the ordering, and a menu that couldn't name the
 * current sort would leave the list looking arbitrarily ordered.
 */
export function sortOptionsFrom(
  columns: RenderColumn[],
  activeSortBy?: RankingSortKey,
  t?: TFunction,
): SortOption<RankingSortKey>[] {
  const options = columns
    .filter((c): c is RenderColumn & { sortKey: RankingSortKey } => c.sortKey !== null)
    .map((c) => ({ key: c.sortKey, label: c.label }))

  if (activeSortBy && t && !options.some((o) => o.key === activeSortBy)) {
    const hidden = RANKING_COLUMNS.find((c) => c.sortKey === activeSortBy)
    if (hidden) options.push({ key: activeSortBy, label: columnLabel(hidden, t) })
  }
  return options
}
