// Custom hook: fetch the AI insight analysis for a ticker.
// Computed by the backend's built-in engine (no external AI services), so it
// is fast and safe to load together with the rest of the detail page. The
// user's saved Scanner settings are sent along so the second opinion judges
// the same signals the chart shows.

import { useEffect, useState } from 'react'
import { fetchAiAnalysis, type ApiAiAnalysis } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseAiAnalysisResult {
  data: ApiAiAnalysis | null
  loading: boolean
  error: string | null
}

export function useAiAnalysis(ticker: string | null): UseAiAnalysisResult {
  const [data, setData] = useState<ApiAiAnalysis | null>(null)
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
    setData(null)

    fetchAiAnalysis(ticker, settingsQueryValue())
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
  }, [ticker])

  return { data, loading, error }
}
