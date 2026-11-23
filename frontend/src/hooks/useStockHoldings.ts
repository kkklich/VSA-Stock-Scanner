import { useEffect, useMemo, useState } from 'react'
import { portfolioRequest, type StockHoldings } from '../api/portfoliosApi'
import { useAuth } from './useAuth'

export function useStockHoldings(ticker: string) {
  const { user, loading } = useAuth()
  const owner = loading ? undefined : user?.id
  const [attempt, setAttempt] = useState(0)
  const request = useMemo(() => ({ owner, ticker, attempt }), [owner, ticker, attempt])
  const [result, setResult] = useState<{
    request: typeof request; holdings: StockHoldings | 'error'
  } | null>(null)

  useEffect(() => {
    if (request.owner === undefined) return
    const { owner, ticker } = request
    const controller = new AbortController()
    portfolioRequest<StockHoldings>('GET', `/holdings/${encodeURIComponent(ticker)}`, undefined, controller.signal, owner)
      .then(holdings => {
        if (!controller.signal.aborted) setResult({ request, holdings })
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ request, holdings: 'error' })
      })
    return () => controller.abort()
  }, [request])

  return {
    owner,
    holdings: result?.request === request ? result.holdings : null,
    retry: () => setAttempt(previous => previous + 1),
  }
}
