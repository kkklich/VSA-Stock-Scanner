// Custom hook: the VSA V4 program's trade simulation for one ticker.
// Computed by the backend from stored bars (no external services); re-fetched
// when the ticker or the long-only / long-and-short choice changes.

import { useEffect, useState } from 'react'
import {
  fetchTradeSimulation,
  type ApiTradeSimulation,
  type SimulationSides,
} from '../api/stocksApi'

export interface UseTradeSimulationResult {
  data: ApiTradeSimulation | null
  loading: boolean
  error: string | null
}

export function useTradeSimulation(
  ticker: string | null,
  sides: SimulationSides,
): UseTradeSimulationResult {
  const [data, setData] = useState<ApiTradeSimulation | null>(null)
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

    fetchTradeSimulation(ticker, sides)
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
  }, [ticker, sides])

  return { data, loading, error }
}
