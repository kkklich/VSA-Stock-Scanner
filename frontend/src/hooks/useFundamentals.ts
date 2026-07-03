// Custom hook: fetch company fundamentals (market cap, P/E, EPS, …).
// A 404 just means no data is available for this ticker — treated as an
// empty result, not an error banner.

import { useEffect, useState } from 'react'
import { fetchFundamentals, type ApiFundamentals } from '../api/stocksApi'
import { ApiError } from '../api/client'

export interface UseFundamentalsResult {
  data: ApiFundamentals | null
  loading: boolean
}

export function useFundamentals(ticker: string | null): UseFundamentalsResult {
  const [data, setData] = useState<ApiFundamentals | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setData(null)

    fetchFundamentals(ticker)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!(err instanceof ApiError && err.status === 404)) {
            console.warn('Fundamentals unavailable:', err)
          }
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [ticker])

  return { data, loading }
}
