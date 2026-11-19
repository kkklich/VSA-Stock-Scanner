import { expect, it, vi } from 'vitest'
import { fetchSignals, type ApiStockSignals } from '../api/stocksApi'
import { renderHook, waitFor } from '../test/utils'
import { useStockDetail } from './useStockDetail'

vi.mock('../api/stocksApi', () => ({ fetchSignals: vi.fn() }))
vi.mock('./useDataVersion', () => ({ useDataVersion: () => 0 }))

function quote(ticker: string, lastPrice: number): ApiStockSignals {
  return {
    ticker, lastPrice, name: null, sector: null, priceChangePct: 0,
    currentRating: 50, ratingChange: 0, history: [], vsaSignals: [], methodSignals: [],
    interval: '1d', intraday: false, historyStart: null,
    weeklyRating: null, weeklySignal: null, weeklyAgreement: null,
  }
}

it('accepts a canonical quote for an alias and clears it in the first render for a different stock', async () => {
  vi.mocked(fetchSignals)
    .mockResolvedValueOnce(quote('DAD', 10))
    .mockResolvedValueOnce(quote('KGH', 50))
  const seen = vi.fn()
  const { result, rerender } = renderHook(({ ticker }) => {
    const detail = useStockDetail(ticker)
    seen(detail.data?.ticker)
    return detail
  }, { initialProps: { ticker: 'dada' } })
  await waitFor(() => expect(result.current.data?.ticker).toBe('DAD'))

  seen.mockClear()
  rerender({ ticker: 'kgh' })
  expect(seen).toHaveBeenNthCalledWith(1, undefined)
  await waitFor(() => expect(result.current.data?.ticker).toBe('KGH'))
})
