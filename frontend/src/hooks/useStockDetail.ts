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
import type { Candle } from '../types'
import { useDataVersion } from './useDataVersion'

/**
 * The same finished history as before? Then the page keeps the very same
 * candles array, and the chart holds the reader's zoom instead of re-fitting
 * each time today's live price moves.
 */
function sameHistory(a: Candle[], b: Candle[]): boolean {
  if (a.length !== b.length) return false
  if (a.length === 0) return true
  const [firstA, lastA] = [a[0], a[a.length - 1]]
  const [firstB, lastB] = [b[0], b[b.length - 1]]
  return (
    firstA.time === firstB.time &&
    lastA.time === lastB.time &&
    lastA.close === lastB.close &&
    lastA.volume === lastB.volume
  )
}

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
  // Moves when the server's data changes (today's live price, the evening
  // refresh); the page then reloads quietly — see `quiet` below.
  const version = useDataVersion()
  const loaded = useRef<string | null>(null)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    // Same request as the one on screen, re-asked only because the data
    // changed: no loading state, and a failure keeps the page as it is.
    const request = `${ticker}|${fromDate ?? ''}|${interval ?? ''}`
    const quiet = loaded.current === request
    loaded.current = request
    if (!quiet) {
      setLoading(true)
      setError(null)
      setNoDataForInterval(false)
    }
    // Clear the chart only when switching companies; when only the time range
    // changes, keep the current chart on screen while the new one loads.
    if (lastTickerRef.current !== ticker) {
      lastTickerRef.current = ticker
      setData(null)
    }

    fetchSignals(ticker, fromDate, undefined, settingsQueryValue(), interval)
      .then((result) => {
        if (!cancelled) {
          setData((prev) =>
            quiet && prev && sameHistory(prev.history, result.history)
              ? { ...result, history: prev.history }
              : result,
          )
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled && !quiet) {
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
  }, [ticker, fromDate, interval, version])

  return { data, loading, error, noDataForInterval }
}
