// Custom hook: fetch scanner back-test stats and manage loading / error state.
// Re-fetches whenever the serialized VSA settings change, so the effectiveness
// table always reflects the thresholds currently configured in the tuner.

import { useEffect, useState } from 'react'
import { fetchScannerStats, type ApiSignalEffectiveness } from '../api/stocksApi'

export interface UseScannerStatsResult {
  data: ApiSignalEffectiveness[] | null
  loading: boolean
  error: string | null
}

export function useScannerStats(settings?: string): UseScannerStatsResult {
  const [data, setData] = useState<ApiSignalEffectiveness[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchScannerStats(settings)
      .then((items) => {
        if (!cancelled) {
          setData(items)
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
  }, [settings])

  return { data, loading, error }
}
