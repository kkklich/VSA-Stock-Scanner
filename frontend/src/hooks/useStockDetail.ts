// Custom hook: fetch signals + OHLCV for a single ticker.
// The user's saved Scanner settings are sent along so the chart overlay is
// detected with the same VSA rules the user configured.

import { useEffect, useRef, useState } from 'react'
import { fetchSignals, type ApiStockSignals } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseStockDetailResult {
  data: ApiStockSignals | null
  loading: boolean
  error: string | null
}

export function useStockDetail(
  ticker: string | null,
  fromDate?: string,
): UseStockDetailResult {
  const [data, setData] = useState<ApiStockSignals | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lastTickerRef = useRef<string | null>(null)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    // Clear the chart only when switching companies; when only the time range
    // changes, keep the current chart on screen while the new one loads.
    if (lastTickerRef.current !== ticker) {
      lastTickerRef.current = ticker
      setData(null)
    }

    fetchSignals(ticker, fromDate, undefined, settingsQueryValue())
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
  }, [ticker, fromDate])

  return { data, loading, error }
}
