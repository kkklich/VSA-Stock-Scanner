// Custom hook: fetch the VSA trust score (prediction accuracy) for a ticker.
// Computed by the backend's built-in back-test (no external AI services), so
// it is fast and safe to load together with the rest of the detail page. The
// user's saved Scanner settings are sent along so the score judges the same
// signals the chart shows.

import { useEffect, useState } from 'react'
import { fetchTrustScore, type ApiTrustScore } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseTrustScoreResult {
  data: ApiTrustScore | null
  loading: boolean
  error: string | null
}

export function useTrustScore(ticker: string | null): UseTrustScoreResult {
  const [data, setData] = useState<ApiTrustScore | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setData(null)

    fetchTrustScore(ticker, settingsQueryValue())
      .then((result) => {
        if (!cancelled) {
          setData(result)
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
  }, [ticker])

  return { data, loading, error }
}
