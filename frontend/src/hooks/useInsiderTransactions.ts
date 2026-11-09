// Custom hook: fetch reported insider purchases and sales for one stock
// (Yahoo Finance for US/UK, GPW ESPI MAR Art. 19 for Polish stocks).

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  fetchInsiderTransactions,
  type ApiInsiderTransactionsResponse,
} from '../api/stocksApi'
import { ApiError } from '../api/client'

export interface UseInsiderTransactionsResult {
  data: ApiInsiderTransactionsResponse | null
  loading: boolean
  error: string | null
  refresh: () => void
}

export function useInsiderTransactions(
  ticker: string | null,
  includeAll = false,
): UseInsiderTransactionsResult {
  const { t } = useTranslation()
  const [data, setData] = useState<ApiInsiderTransactionsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [reload, setReload] = useState(0)
  const pendingRefresh = useRef<string | null>(null)
  const refresh = useCallback(() => {
    if (!ticker) return
    pendingRefresh.current = ticker
    setReload((value) => value + 1)
  }, [ticker])

  useEffect(() => {
    if (!ticker) {
      setData(null)
      setLoading(false)
      setFailed(false)
      pendingRefresh.current = null
      return
    }

    let cancelled = false
    const forceRefresh = pendingRefresh.current === ticker
    pendingRefresh.current = null
    setData((previous) => forceRefresh && previous?.ticker.toLowerCase() === ticker.toLowerCase()
      ? previous
      : null)
    setLoading(true)
    setFailed(false)

    fetchInsiderTransactions(ticker, { includeAll, ...(forceRefresh ? { refresh: true } : {}) })
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          if (!(err instanceof ApiError && err.status === 404)) {
            console.warn('Insider transactions unavailable:', err)
            setFailed(true)
          }
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [ticker, includeAll, reload])

  return { data, loading, error: failed ? t('insider.loadError') : null, refresh }
}
