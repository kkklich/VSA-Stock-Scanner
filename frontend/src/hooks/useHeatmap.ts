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

export function useHeatmap(): UseHeatmapResult {
  const [data, setData] = useState<ApiHeatmapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchHeatmap(settingsQueryValue())
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
  }, [tick])

  return { data, loading, error, refetch: () => setTick((t) => t + 1) }
}
