// Custom hook: fetch one stock's multi-day relative-volume (RVOL) reading —
// the single-ticker form of the /volume-surge screen. Independent of the chart
// range, so it is fetched once per ticker and does not recompute as the user
// scrolls/zooms the chart. A 404 (no price history) is treated as "no data",
// not an error banner.

import { useEffect, useState } from 'react'
import { fetchTickerVolume, type ApiTickerVolume } from '../api/stocksApi'
import { ApiError } from '../api/client'

export interface UseTickerVolumeResult {
  data: ApiTickerVolume | null
  loading: boolean
}

export function useTickerVolume(ticker: string | null): UseTickerVolumeResult {
  const [data, setData] = useState<ApiTickerVolume | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setData(null)

    fetchTickerVolume(ticker)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!(err instanceof ApiError && err.status === 404)) {
            console.warn('Volume reading unavailable:', err)
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
