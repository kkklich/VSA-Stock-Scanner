// Fetch the trading-method catalogue (GET /api/stocks/methods) once, for the
// dashboard's method selector. The catalogue is small and static per build, so
// a single fetch on mount is plenty.

import { useEffect, useState } from 'react'
import { fetchMethods, type ApiTradingMethod } from '../api/stocksApi'

export interface UseMethodsResult {
  methods: ApiTradingMethod[]
  loading: boolean
  error: string | null
}

export function useMethods(): UseMethodsResult {
  const [methods, setMethods] = useState<ApiTradingMethod[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchMethods()
      .then((m) => {
        if (!cancelled) {
          setMethods(m)
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
  }, [])

  return { methods, loading, error }
}
