// Custom hook: fetch the consolidated analytics-opinion summary for a ticker.
// The backend fuses the VSA verdict, the AI Insight second opinion, the Signal
// Trust Score and every trading method into one plain-language read — computed
// locally (no external AI services), so it is fast and safe to load with the
// rest of the detail page. The user's saved Scanner settings are sent along so
// the summary judges the same signals the chart shows.

import { useEffect, useState } from 'react'
import { fetchOpinionSummary, type ApiAnalyticsSummary } from '../api/stocksApi'
import { settingsQueryValue } from '../lib/vsaSettings'

export interface UseOpinionSummaryResult {
  data: ApiAnalyticsSummary | null
  loading: boolean
  error: string | null
}

export function useOpinionSummary(ticker: string | null): UseOpinionSummaryResult {
  const [data, setData] = useState<ApiAnalyticsSummary | null>(null)
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

    fetchOpinionSummary(ticker, settingsQueryValue())
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
