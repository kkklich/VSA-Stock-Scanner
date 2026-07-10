// Custom hook: fetch one page of the VSA ranking with server-side sorting,
// searching, filtering and pagination. The user's saved Scanner settings are
// sent along so the backend ranks with the same VSA rules the user configured.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchRanking,
  type ApiRankingItem,
  type RankingQuery,
} from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseRankingResult {
  data: ApiRankingItem[] | null
  /** Total number of rows matching the query (across all pages). */
  total: number
  loading: boolean
  error: string | null
  /** Re-fetch on demand (e.g. after the user clicks "Refresh"). */
  refetch: () => void
}

/** Everything the caller controls; `settings` is added automatically. */
export type RankingParams = Omit<RankingQuery, 'settings'>

export function useRanking(params: RankingParams = {}): UseRankingResult {
  const [data, setData] = useState<ApiRankingItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  // Serialise the params so the effect only re-runs when a value actually
  // changes (a fresh object literal every render would otherwise loop).
  const key = useMemo(() => JSON.stringify(params), [params])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const query: RankingQuery = { ...params, settings: settingsQueryValue() }
    fetchRanking(query)
      .then(({ items, total: t }) => {
        if (!cancelled) {
          setData(items)
          setTotal(t)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unknown error')
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick])

  return { data, total, loading, error, refetch: () => setTick((t) => t + 1) }
}

/* ── Infinite-scroll variant ────────────────────────────────────────────────
 * Same query surface as useRanking, but pages accumulate instead of replacing
 * each other: `loadMore()` appends the next page to `items`. Used by the
 * Dashboard, where the user scrolls to reveal more rows instead of paging.
 */

export interface UseInfiniteRankingResult {
  /** All rows fetched so far (page 1..n concatenated); null until first load. */
  items: ApiRankingItem[] | null
  /** Total number of rows matching the query (across all pages). */
  total: number
  /** True while the first page (or a reset) is loading. */
  loading: boolean
  /** True while an additional page is being appended. */
  loadingMore: boolean
  /** True when more rows exist beyond what has been fetched. */
  hasMore: boolean
  error: string | null
  /** Fetch the next page and append it. No-op while a fetch is in flight. */
  loadMore: () => void
  /** Reset to page 1 and re-fetch (e.g. after a data refresh). */
  refetch: () => void
}

/** `page` is managed internally — everything else works like useRanking. */
export type InfiniteRankingParams = Omit<RankingParams, 'page'>

export function useInfiniteRanking(
  params: InfiniteRankingParams = {},
): UseInfiniteRankingResult {
  const [items, setItems] = useState<ApiRankingItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [tick, setTick] = useState(0)

  // Guards loadMore against duplicate calls (e.g. an IntersectionObserver
  // firing twice) before React has re-rendered with the in-flight state.
  const inFlight = useRef(false)

  const key = useMemo(() => JSON.stringify(params), [params])

  // Reset to page 1 synchronously when the query shape changes, so the fetch
  // effect never runs for a stale (key, page) combination.
  const [prevKey, setPrevKey] = useState(key)
  if (key !== prevKey) {
    setPrevKey(key)
    setPage(1)
    inFlight.current = false
  }

  useEffect(() => {
    let cancelled = false
    inFlight.current = true
    if (page === 1) {
      setLoading(true)
    } else {
      setLoadingMore(true)
    }
    setError(null)

    const query: RankingQuery = { ...params, page, settings: settingsQueryValue() }
    fetchRanking(query)
      .then(({ items: pageItems, total: t }) => {
        if (cancelled) return
        setItems((prev) =>
          page === 1 || prev === null ? pageItems : [...prev, ...pageItems],
        )
        setTotal(t)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unknown error')
        }
      })
      .finally(() => {
        if (!cancelled) {
          inFlight.current = false
          setLoading(false)
          setLoadingMore(false)
        }
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, page, tick])

  const loadMore = useCallback(() => {
    if (inFlight.current) return
    inFlight.current = true
    setPage((p) => p + 1)
  }, [])

  const refetch = useCallback(() => {
    setPage(1)
    setTick((t) => t + 1)
  }, [])

  const hasMore = items !== null && items.length < total

  return { items, total, loading, loadingMore, hasMore, error, loadMore, refetch }
}
