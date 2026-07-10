// Custom hook: fetch the stored VSA rating history for one ticker.
// Backed by GET /api/stocks/{ticker}/rating-history — daily snapshots saved by
// the refresh pipeline (or derived on the fly when none are stored yet).

import { useEffect, useState } from 'react'
import { fetchRatingHistory, type ApiRatingHistory } from '../api/stocksApi'

export interface UseRatingHistoryResult {
  data: ApiRatingHistory | null
  loading: boolean
  error: string | null
}

export function useRatingHistory(ticker: string): UseRatingHistoryResult {
  const [data, setData] = useState<ApiRatingHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setData(null)

    fetchRatingHistory(ticker)
      .then((res) => {
        if (!cancelled) {
          setData(res)
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
