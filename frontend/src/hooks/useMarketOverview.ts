// Custom hook: fetch the Dashboard's market overview (breadth + biggest rating
// movers) for the market the top bar names. Same shape as `useHeatmap`: the
// user's saved Scanner settings ride along so the ratings match the ranking
// below, and the numbers reload quietly when the server's data changes.

import { useEffect, useRef, useState } from 'react'
import { fetchMarketOverview, type ApiMarketOverview } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'
import { useDataVersion } from './useDataVersion'

export interface UseMarketOverviewResult {
  data: ApiMarketOverview | null
  loading: boolean
  error: string | null
}

/** `market` null holds the request (the market list is still resolving). */
export function useMarketOverview(market: string | null): UseMarketOverviewResult {
  const [data, setData] = useState<ApiMarketOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const version = useDataVersion()
  const loaded = useRef<string | null>(null)

  useEffect(() => {
    if (market === null) return
    let cancelled = false
    // A reload for the same market (new data arrived) keeps the numbers on
    // screen; only a different market shows the loading state.
    const quiet = loaded.current === market
    loaded.current = market
    if (!quiet) {
      setLoading(true)
      setError(null)
    }

    // The GPW is the backend default; leaving it out keeps the request as it was.
    fetchMarketOverview(settingsQueryValue(), market === 'gpw' ? undefined : market)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled && !quiet) {
          setError(err instanceof Error ? err.message : 'Unknown error')
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [market, version])

  return { data, loading, error }
}
