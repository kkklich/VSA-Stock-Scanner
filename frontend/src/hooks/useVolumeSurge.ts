// Custom hook: fetch the volume-surge scan and manage loading / error state.
// Refetches whenever the screen parameters change; the user's saved Scanner
// settings are sent along so VSA ratings match the other pages.

import { useEffect, useState } from 'react'
import {
  fetchVolumeSurge,
  type ApiVolumeSurgeResponse,
  type VolumeSurgeQuery,
} from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseVolumeSurgeResult {
  data: ApiVolumeSurgeResponse | null
  loading: boolean
  error: string | null
  /** Re-fetch on demand (e.g. after a data refresh completes). */
  refetch: () => void
}

export function useVolumeSurge(
  query: Omit<VolumeSurgeQuery, 'settings'>,
): UseVolumeSurgeResult {
  const [data, setData] = useState<ApiVolumeSurgeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const { recentDays, baselineDays, minRatio, page, pageSize, sortBy, sortDir } =
    query

  useEffect(() => {
    let cancelled = false
    setLoading(true)
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
        if (!cancelled) {
          setData(resp)
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
  }, [recentDays, baselineDays, minRatio, page, pageSize, sortBy, sortDir, tick])

  return { data, loading, error, refetch: () => setTick((t) => t + 1) }
}
