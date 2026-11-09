import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchInsiderTransactions, type ApiInsiderTransactionsResponse } from '../api/stocksApi'
import { useInsiderTransactions } from './useInsiderTransactions'

vi.mock('../api/stocksApi', () => ({ fetchInsiderTransactions: vi.fn() }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

const response = (ticker: string): ApiInsiderTransactionsResponse => ({
  ticker, name: ticker, market: 'gpw', currency: 'PLN',
  summary: {
    totalPurchasesCount: 0, totalSalesCount: 0, totalPurchasesShares: 0,
    totalSalesShares: 0, totalPurchasesValue: 0, totalSalesValue: 0,
    netShares: 0, netValue: 0, currency: 'PLN',
  },
  transactions: [], chartMarkers: [], byInsider: [], warnings: [],
})

beforeEach(() => vi.mocked(fetchInsiderTransactions).mockReset())
afterEach(() => vi.restoreAllMocks())

describe('useInsiderTransactions', () => {
  it('refreshes ESPI explicitly without forcing later filter requests', async () => {
    vi.mocked(fetchInsiderTransactions).mockResolvedValue(response('CBF'))
    const { result, rerender } = renderHook(
      ({ all }) => useInsiderTransactions('cbf', all), { initialProps: { all: false } },
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchInsiderTransactions).toHaveBeenLastCalledWith('cbf', { includeAll: false })

    act(() => result.current.refresh())
    await waitFor(() => expect(fetchInsiderTransactions).toHaveBeenCalledTimes(2))
    expect(fetchInsiderTransactions).toHaveBeenLastCalledWith('cbf', {
      includeAll: false, refresh: true,
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    rerender({ all: true })
    await waitFor(() => expect(fetchInsiderTransactions).toHaveBeenCalledTimes(3))
    expect(fetchInsiderTransactions).toHaveBeenLastCalledWith('cbf', { includeAll: true })
  })

  it('shows a fetch error and keeps existing records when a refresh fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.mocked(fetchInsiderTransactions)
      .mockResolvedValueOnce(response('CBF'))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(response('CBF'))
    const { result } = renderHook(() => useInsiderTransactions('cbf'))
    await waitFor(() => expect(result.current.data?.ticker).toBe('CBF'))

    act(() => result.current.refresh())
    await waitFor(() => expect(result.current.error).toBe('insider.loadError'))
    expect(result.current.data?.ticker).toBe('CBF')
    expect(result.current.loading).toBe(false)

    act(() => result.current.refresh())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBeNull()
  })

  it('ignores the previous ticker response after switching to another company', async () => {
    let finishOld!: (data: ApiInsiderTransactionsResponse) => void
    vi.mocked(fetchInsiderTransactions)
      .mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve }))
      .mockResolvedValueOnce(response('PKO'))
    const { result, rerender } = renderHook(
      ({ ticker }) => useInsiderTransactions(ticker), { initialProps: { ticker: 'cbf' } },
    )
    rerender({ ticker: 'pko' })
    await waitFor(() => expect(result.current.data?.ticker).toBe('PKO'))
    await act(async () => finishOld(response('CBF')))
    expect(result.current.data?.ticker).toBe('PKO')
  })

  it('clears a pending load when the ticker is removed', async () => {
    vi.mocked(fetchInsiderTransactions).mockImplementation(() => new Promise(() => {}))
    const { result, rerender } = renderHook(
      ({ ticker }: { ticker: string | null }) => useInsiderTransactions(ticker),
      { initialProps: { ticker: 'cbf' as string | null } },
    )
    expect(result.current.loading).toBe(true)
    rerender({ ticker: null })
    expect(result.current.loading).toBe(false)
    expect(result.current.data).toBeNull()
    act(() => result.current.refresh())
    expect(fetchInsiderTransactions).toHaveBeenCalledTimes(1)
  })
})
