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

/** `market` null holds the request (the market is still being resolved). */
export function useScannerStats(
  settings?: string,
  market: string | null = 'gpw',
): UseScannerStatsResult {
  const [data, setData] = useState<ApiSignalEffectiveness[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (market === null) return
    let cancelled = false
    setLoading(true)
    setError(null)

    // The GPW is the backend default; leaving it out keeps the request as it was.
    fetchScannerStats(settings, market === 'gpw' ? undefined : market)
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
  }, [settings, market])

  return { data, loading, error }
}
