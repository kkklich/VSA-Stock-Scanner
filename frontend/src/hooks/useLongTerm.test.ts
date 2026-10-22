import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  LONG_TERM_REQUEST_TIMEOUT_MS, resetLongTermCacheForTests,
  useFinancialHistory, useLongTermHistory, useLongTermRanking,
} from './useLongTerm'

const mocks = vi.hoisted(() => ({ ranking: vi.fn(), scores: vi.fn(), financials: vi.fn(), version: 0 }))
vi.mock('../api/longTermApi', () => ({ fetchLongTermRanking: mocks.ranking, fetchLongTermHistory: mocks.scores, fetchFinancialHistory: mocks.financials }))
vi.mock('./useDataVersion', () => ({ useDataVersion: () => mocks.version }))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
beforeEach(() => { vi.resetAllMocks(); resetLongTermCacheForTests(); mocks.version = 0 })
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('long-term data loading', () => {
  it('aborts an old market request and ignores its late response', async () => {
    const gpw = deferred<unknown>(), us = deferred<unknown>()
    mocks.ranking.mockImplementation((market: string) => market === 'gpw' ? gpw.promise : us.promise)
    const { result, rerender, unmount } = renderHook(({ market }) => useLongTermRanking(market), { initialProps: { market: 'gpw' } })
    const firstSignal = mocks.ranking.mock.calls[0][1] as AbortSignal
    rerender({ market: 'us' })
    expect(firstSignal.aborted).toBe(true)
    expect(result.current.data).toBeNull()
    expect(result.current.lastUpdated).toBeNull()
    expect(result.current.stale).toBe(false)
    await act(async () => { us.resolve({ market: 'us', items: [] }) })
    expect(result.current.data?.market).toBe('us')
    await act(async () => { gpw.resolve({ market: 'gpw', items: [] }) })
    expect(result.current.data?.market).toBe('us')
    unmount()
    expect((mocks.ranking.mock.calls[1][1] as AbortSignal).aborted).toBe(true)
  })

  it('keeps current results during refresh and invalidates them on dataVersion', async () => {
    mocks.ranking.mockResolvedValue({ market: 'gpw', items: [] })
    const { result, rerender } = renderHook(() => useLongTermRanking('gpw'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    const fresh = deferred<unknown>()
    mocks.ranking.mockReturnValue(fresh.promise)
    mocks.version += 1
    rerender()
    expect(result.current.data?.market).toBe('gpw')
    expect(result.current.loading).toBe(true)
    await act(async () => { fresh.resolve({ market: 'gpw', items: [], scoredCount: 5 }) })
    expect(result.current.data?.scoredCount).toBe(5)
  })

  it('does not request an unselected ticker and resets when a different ticker is selected', async () => {
    mocks.scores.mockResolvedValue({ ticker: 'kgh', dbEnabled: true, items: [] })
    const { result, rerender } = renderHook(({ ticker }) => useLongTermHistory(ticker), { initialProps: { ticker: null as string | null } })
    expect(mocks.scores).not.toHaveBeenCalled()
    rerender({ ticker: 'kgh' })
    await waitFor(() => expect(result.current.data?.ticker).toBe('kgh'))
    const pending = deferred<unknown>()
    mocks.scores.mockReturnValue(pending.promise)
    rerender({ ticker: 'aapl.us' })
    expect(result.current.data).toBeNull()
    await act(async () => { pending.resolve({ ticker: 'aapl.us', dbEnabled: true, items: [] }) })
    expect(result.current.data?.ticker).toBe('aapl.us')
  })

  it('retries a failed financial history request', async () => {
    mocks.financials.mockRejectedValueOnce(new Error('unavailable')).mockResolvedValue({ ticker: 'kgh', dbEnabled: true, items: [] })
    const { result } = renderHook(() => useFinancialHistory('kgh'))
    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.stale).toBe(false)
    expect(result.current.lastUpdated).toBeNull()
    act(() => result.current.refetch())
    await waitFor(() => expect(result.current.data?.ticker).toBe('kgh'))
    expect(result.current.error).toBe(false)
  })

  it('retains last successful data and load time through failed refresh and manual recovery', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-22T16:00:00Z'))
    const first = deferred<unknown>(), failed = deferred<unknown>(), recovered = deferred<unknown>()
    mocks.ranking.mockReturnValueOnce(first.promise).mockReturnValueOnce(failed.promise).mockReturnValueOnce(recovered.promise)
    const { result } = renderHook(() => useLongTermRanking('gpw'))
    await act(async () => { first.resolve({ market: 'gpw', asOf: '2026-10-21', items: [], scoredCount: 5 }) })
    const original = result.current.data
    expect(result.current.lastUpdated).toBe('2026-10-22T16:00:00.000Z')
    act(() => result.current.refetch())
    expect(result.current.data).toBe(original)
    expect(result.current.loading).toBe(true)
    await act(async () => { failed.reject(new Error('offline')) })
    expect(result.current).toMatchObject({ data: original, error: true, stale: true, loading: false, lastUpdated: '2026-10-22T16:00:00.000Z' })
    act(() => result.current.refetch())
    expect(result.current).toMatchObject({ data: original, error: false, stale: true, loading: true })
    vi.setSystemTime(new Date('2026-10-22T16:05:00Z'))
    await act(async () => { recovered.resolve({ market: 'gpw', items: [], scoredCount: 6 }) })
    expect(result.current).toMatchObject({ error: false, stale: false, loading: false, lastUpdated: '2026-10-22T16:05:00.000Z' })
    expect(result.current.data?.scoredCount).toBe(6)
  })

  it('ends an unresponsive request at the deadline and ignores a late response after retry', async () => {
    vi.useFakeTimers()
    const hung = deferred<unknown>(), retried = deferred<unknown>()
    mocks.ranking.mockReturnValueOnce(hung.promise).mockReturnValueOnce(retried.promise)
    const { result } = renderHook(() => useLongTermRanking('gpw'))
    const signal = mocks.ranking.mock.calls[0][1] as AbortSignal
    await act(async () => { await vi.advanceTimersByTimeAsync(LONG_TERM_REQUEST_TIMEOUT_MS) })
    expect(signal.aborted).toBe(true)
    expect(result.current).toMatchObject({ data: null, error: true, stale: false, loading: false, lastUpdated: null })
    act(() => result.current.refetch())
    await act(async () => { retried.resolve({ market: 'gpw', items: [], scoredCount: 6 }) })
    const loadedAt = result.current.lastUpdated
    await act(async () => { hung.resolve({ market: 'gpw', items: [], scoredCount: 1 }) })
    expect(result.current.data?.scoredCount).toBe(6)
    expect(result.current.lastUpdated).toBe(loadedAt)
    expect(result.current.error).toBe(false)
  })

  it('keeps cached results and marks them stale when a refresh times out', async () => {
    vi.useFakeTimers()
    mocks.ranking.mockResolvedValueOnce({ market: 'gpw', items: [] }).mockImplementation(() => new Promise(() => {}))
    const { result } = renderHook(() => useLongTermRanking('gpw'))
    await act(async () => {})
    const loadedAt = result.current.lastUpdated
    act(() => result.current.refetch())
    await act(async () => { await vi.advanceTimersByTimeAsync(LONG_TERM_REQUEST_TIMEOUT_MS) })
    expect(result.current.data?.market).toBe('gpw')
    expect(result.current).toMatchObject({ error: true, stale: true, loading: false, lastUpdated: loadedAt })
  })

  it('restores only the same resource and key on revisit and preserves the original load time', async () => {
    mocks.ranking.mockResolvedValueOnce({ market: 'gpw', items: [], scoredCount: 5 })
    const first = renderHook(() => useLongTermRanking('gpw'))
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    const loadedAt = first.result.current.lastUpdated
    first.unmount()
    mocks.ranking.mockImplementation(() => new Promise(() => {}))
    const revisited = renderHook(() => useLongTermRanking('gpw'))
    expect(revisited.result.current.data?.scoredCount).toBe(5)
    expect(revisited.result.current).toMatchObject({ loading: true, stale: false, lastUpdated: loadedAt })
    const otherMarket = renderHook(() => useLongTermRanking('us'))
    expect(otherMarket.result.current.data).toBeNull()
    expect(otherMarket.result.current.lastUpdated).toBeNull()
    mocks.scores.mockImplementation(() => new Promise(() => {}))
    const otherResource = renderHook(() => useLongTermHistory('gpw'))
    expect(otherResource.result.current.data).toBeNull()
    expect(otherResource.result.current.lastUpdated).toBeNull()
  })

  it('retains a failed-refresh warning on remount until fresh data arrives', async () => {
    mocks.ranking.mockResolvedValueOnce({ market: 'gpw', items: [] }).mockRejectedValueOnce(new Error('offline'))
    const first = renderHook(() => useLongTermRanking('gpw'))
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    act(() => first.result.current.refetch())
    await waitFor(() => expect(first.result.current.stale).toBe(true))
    first.unmount()
    const pending = deferred<unknown>()
    mocks.ranking.mockReturnValue(pending.promise)
    const revisited = renderHook(() => useLongTermRanking('gpw'))
    expect(revisited.result.current).toMatchObject({ loading: true, stale: true, error: false })
    await act(async () => { pending.resolve({ market: 'gpw', items: [] }) })
    expect(revisited.result.current.stale).toBe(false)
  })

  it('cancels deadlines on key changes and unmount without errors or cache writes', async () => {
    vi.useFakeTimers()
    const old = deferred<unknown>()
    mocks.scores.mockReturnValue(old.promise)
    const { result, rerender, unmount } = renderHook(({ ticker }) => useLongTermHistory(ticker), { initialProps: { ticker: 'old' as string | null } })
    const signal = mocks.scores.mock.calls[0][1] as AbortSignal
    rerender({ ticker: null })
    expect(signal.aborted).toBe(true)
    await act(async () => { await vi.advanceTimersByTimeAsync(LONG_TERM_REQUEST_TIMEOUT_MS) })
    expect(result.current).toMatchObject({ data: null, lastUpdated: null, loading: false, error: false, stale: false })
    unmount()
    await act(async () => { old.resolve({ ticker: 'old', dbEnabled: true, items: [] }) })
    mocks.scores.mockImplementation(() => new Promise(() => {}))
    const again = renderHook(() => useLongTermHistory('old'))
    expect(again.result.current.data).toBeNull()
    expect(again.result.current.lastUpdated).toBeNull()
  })

  it('bounds each resource cache and keeps recently used keys', async () => {
    mocks.scores.mockImplementation((ticker: string) => Promise.resolve({ ticker, dbEnabled: true, items: [] }))
    for (let i = 0; i < 33; i += 1) {
      const hook = renderHook(() => useLongTermHistory(`stock${i}`))
      await act(async () => {})
      hook.unmount()
    }
    mocks.scores.mockImplementation(() => new Promise(() => {}))
    const oldest = renderHook(() => useLongTermHistory('stock0'))
    expect(oldest.result.current.data).toBeNull()
    const recent = renderHook(() => useLongTermHistory('stock32'))
    expect(recent.result.current.data?.ticker).toBe('stock32')
  })
})
