// Custom hook: fetch scanner back-test stats and manage loading / error state.

import { useEffect, useState } from 'react'
import { fetchScannerStats, type ApiSignalEffectiveness } from '../api/stocksApi'

export interface UseScannerStatsResult {
  data: ApiSignalEffectiveness[] | null
  loading: boolean
  error: string | null
}

export function useScannerStats(): UseScannerStatsResult {
  const [data, setData] = useState<ApiSignalEffectiveness[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchScannerStats()
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
  }, [])

  return { data, loading, error }
}
