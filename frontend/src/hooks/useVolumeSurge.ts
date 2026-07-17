// Custom hook: fetch the volume-surge scan with infinite-scroll paging.
// Pages are accumulated — bumping `page` appends the next slice instead of
// replacing it, while any change to the screen parameters / sort resets back
// to page 1 (a fresh list). The user's saved Scanner settings are sent along
// so VSA ratings match the other pages.

import { useEffect, useState } from 'react'
import {
  fetchVolumeSurge,
  type ApiVolumeSurgeItem,
  type ApiVolumeSurgeResponse,
  type VolumeSurgeQuery,
} from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseVolumeSurgeResult {
  /** All rows loaded so far (page 1 … current page). */
  items: ApiVolumeSurgeItem[]
  /** The latest response's metadata (asOf, counts, echoed parameters). */
  meta: ApiVolumeSurgeResponse | null
  /** True while the first page of a fresh query is loading. */
  loading: boolean
  /** True while an additional page is being appended (infinite scroll). */
  loadingMore: boolean
  error: string | null
  /** More rows exist beyond what's loaded — worth fetching the next page. */
  hasMore: boolean
  /** Re-fetch on demand (e.g. after a data refresh, or to retry an error). */
  refetch: () => void
}

export function useVolumeSurge(
  query: Omit<VolumeSurgeQuery, 'settings'>,
): UseVolumeSurgeResult {
  const [items, setItems] = useState<ApiVolumeSurgeItem[]>([])
  const [meta, setMeta] = useState<ApiVolumeSurgeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const { recentDays, baselineDays, minRatio, page, pageSize, sortBy, sortDir } =
    query

  useEffect(() => {
    let cancelled = false
    const firstPage = page === 1
    // Page 1 is a fresh load (show the main spinner); later pages append.
    if (firstPage) setLoading(true)
    else setLoadingMore(true)
    setError(null)

    fetchVolumeSurge({
      recentDays,
      baselineDays,
      minRatio,
      page,
      pageSize,
      sortBy,
      sortDir,
      settings: settingsQueryValue(),
    })
      .then((resp) => {
        if (cancelled) return
        setMeta(resp)
        // Replace on page 1, append on later pages. Appending in the fetch
        // callback (guarded by `cancelled`) runs exactly once per page, so a
        // StrictMode double-mount or a superseded fetch can't duplicate rows.
        setItems((prev) => (firstPage ? resp.items : [...prev, ...resp.items]))
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
  }, [recentDays, baselineDays, minRatio, page, pageSize, sortBy, sortDir, tick])

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
