// Custom hook: fetch the VSA ranking and manage loading / error state.

import { useEffect, useState } from 'react'
import { fetchRanking, type ApiRankingItem } from '../api/stocksApi'

export interface UseRankingResult {
  data: ApiRankingItem[] | null
  loading: boolean
  error: string | null
  /** Re-fetch on demand (e.g. after the user clicks "Refresh"). */
  refetch: () => void
}

export function useRanking(page = 1, pageSize = 50): UseRankingResult {
  const [data, setData] = useState<ApiRankingItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchRanking(page, pageSize)
      .then((items) => {
        if (!cancelled) {
          setData(items)
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
  }, [page, pageSize, tick])

  return { data, loading, error, refetch: () => setTick((t) => t + 1) }
}
