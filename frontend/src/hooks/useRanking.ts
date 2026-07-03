// Custom hook: fetch the VSA ranking and manage loading / error state.
// The user's saved Scanner settings are sent along so the backend ranks
// with the same VSA rules the user configured.

import { useEffect, useState } from 'react'
import { fetchRanking, type ApiRankingItem } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

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

    fetchRanking(page, pageSize, settingsQueryValue())
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
