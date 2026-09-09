// Custom hook: fetch signals + OHLCV for a single ticker.
// The user's saved Scanner settings are sent along so the chart overlay is
// detected with the same VSA rules the user configured.

import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import {
  fetchSignals,
  type ApiStockSignals,
  type ChartInterval,
} from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseStockDetailResult {
  data: ApiStockSignals | null
  loading: boolean
  error: string | null
  /**
   * True when the backend answered 404: this company simply has no history at
   * the requested bar size (Yahoo publishes no intraday candles for many GPW
   * listings). A settled fact, not a failure — the page says so plainly and
   * points at 1D/1W instead of showing a red "failed to load".
   */
  noDataForInterval: boolean
}

export function useStockDetail(
  ticker: string | null,
  fromDate?: string,
  /** Chart bar size; omitted = daily, the endpoint's own default. */
  interval?: ChartInterval,
): UseStockDetailResult {
  const [data, setData] = useState<ApiStockSignals | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [noDataForInterval, setNoDataForInterval] = useState(false)
  const lastTickerRef = useRef<string | null>(null)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setNoDataForInterval(false)
    // Clear the chart only when switching companies; when only the time range
    // changes, keep the current chart on screen while the new one loads.
    if (lastTickerRef.current !== ticker) {
      lastTickerRef.current = ticker
      setData(null)
    }

    fetchSignals(ticker, fromDate, undefined, settingsQueryValue(), interval)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          // A 404 means "this bar size does not exist for this company", which
          // the page presents as information rather than as a failure.
          setNoDataForInterval(err instanceof ApiError && err.status === 404)
          setError(err instanceof Error ? err.message : 'Unknown error')
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [ticker, fromDate, interval])

  return { data, loading, error, noDataForInterval }
}
