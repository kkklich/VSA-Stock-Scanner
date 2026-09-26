// Custom hook: fetch reported insider purchases and sales for one stock
// (Yahoo Finance for US/UK, GPW ESPI MAR Art. 19 for Polish stocks).

import { useEffect, useState } from 'react'
import {
  fetchInsiderTransactions,
  type ApiInsiderTransactionsResponse,
} from '../api/stocksApi'
import { ApiError } from '../api/client'

export interface UseInsiderTransactionsResult {
  data: ApiInsiderTransactionsResponse | null
  loading: boolean
}

export function useInsiderTransactions(
  ticker: string | null,
  includeAll = false,
): UseInsiderTransactionsResult {
  const [data, setData] = useState<ApiInsiderTransactionsResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      return
    }

    let cancelled = false
    setLoading(true)

    fetchInsiderTransactions(ticker, { includeAll })
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
          }
          setData(null)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [ticker, includeAll])

  return { data, loading }
}
