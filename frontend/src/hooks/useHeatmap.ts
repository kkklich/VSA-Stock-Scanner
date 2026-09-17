// Custom hook: fetch the sector-heatmap tiles and manage loading / error state.
// The user's saved Scanner settings are sent along so tile ratings match the
// ranking computed with the same VSA rules.

import { useEffect, useState } from 'react'
import { fetchHeatmap, type ApiHeatmapResponse } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseHeatmapResult {
  data: ApiHeatmapResponse | null
  loading: boolean
  error: string | null
  /** Re-fetch on demand (e.g. after a data refresh completes). */
  refetch: () => void
}

/** Tiles of one market; `market` null holds the request (still resolving). */
export function useHeatmap(market: string | null = 'gpw'): UseHeatmapResult {
  const [data, setData] = useState<ApiHeatmapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (market === null) return
    let cancelled = false
    setLoading(true)
    setError(null)

    // The GPW is the backend default; leaving it out keeps the request as it was.
    fetchHeatmap(settingsQueryValue(), market === 'gpw' ? undefined : market)
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
  }, [tick, market])

  return { data, loading, error, refetch: () => setTick((t) => t + 1) }
}
