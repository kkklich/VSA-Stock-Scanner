// Custom hook: fetch signals + OHLCV for a single ticker.

import { useEffect, useState } from 'react'
import { fetchSignals, type ApiStockSignals } from '../api/stocksApi'

export interface UseStockDetailResult {
  data: ApiStockSignals | null
  loading: boolean
  error: string | null
}

export function useStockDetail(ticker: string | null): UseStockDetailResult {
  const [data, setData] = useState<ApiStockSignals | null>(null)
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

    fetchSignals(ticker)
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
