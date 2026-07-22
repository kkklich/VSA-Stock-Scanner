// Custom hook: fetch the capex screen with infinite-scroll paging.
// Pages are accumulated — bumping `page` appends the next slice instead of
// replacing it, while any change to the filters / sort resets back to page 1
// (a fresh list). Mirrors useVolumeSurge; the capex figures are fundamentals,
// so no VSA settings are involved.

import { useEffect, useState } from 'react'
import {
  fetchCapex,
  type ApiCapexItem,
  type ApiCapexResponse,
  type CapexQuery,
} from '../api/stocksApi'

export interface UseCapexResult {
  /** All rows loaded so far (page 1 … current page). */
  items: ApiCapexItem[]
  /** The latest response's metadata (asOf, counts). */
  meta: ApiCapexResponse | null
  /** True while the first page of a fresh query is loading. */
  loading: boolean
  /** True while an additional page is being appended (infinite scroll). */
  loadingMore: boolean
  error: string | null
  /** More rows exist beyond what's loaded — worth fetching the next page. */
  hasMore: boolean
  /** Re-run the fetch for the current page — meant for retrying after an error. */
  refetch: () => void
}

export function useCapex(query: CapexQuery): UseCapexResult {
  const [items, setItems] = useState<ApiCapexItem[]>([])
  const [meta, setMeta] = useState<ApiCapexResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const { q, sector, currency, withData, page, pageSize, sortBy, sortDir } = query

  useEffect(() => {
    let cancelled = false
    const firstPage = page === 1
    if (firstPage) setLoading(true)
    else setLoadingMore(true)
    setError(null)

    fetchCapex({ q, sector, currency, withData, page, pageSize, sortBy, sortDir })
      .then((resp) => {
        if (cancelled) return
        setMeta(resp)
        // Replace on page 1, append on later pages. Dedupe by ticker: the
        // server's cached screen can be rebuilt between page fetches, shifting
        // a ticker onto a page we already loaded (duplicate React keys).
        setItems((prev) => {
          if (firstPage) return resp.items
          const seen = new Set(prev.map((i) => i.ticker))
          return [...prev, ...resp.items.filter((i) => !seen.has(i.ticker))]
        })
        setLoading(false)
        setLoadingMore(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Unknown error')
        setLoading(false)
        setLoadingMore(false)
      })

    return () => {
      cancelled = true
    }
  }, [q, sector, currency, withData, page, pageSize, sortBy, sortDir, tick])

  const hasMore = meta !== null && items.length < meta.totalCount

  return {
    items,
    meta,
    loading,
    loadingMore,
    error,
    hasMore,
    refetch: () => setTick((t) => t + 1),
  }
}
