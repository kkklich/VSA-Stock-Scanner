import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import type { VolumeSurgeQuery } from '../api/stocksApi'
import { useVolumeSurge } from './useVolumeSurge'

afterEach(() => vi.unstubAllGlobals())

describe('useVolumeSurge favorites requests', () => {
  it('sends the allow-list, refetches on membership changes and keeps empty distinct from all', async () => {
    const fetchMock = vi.fn<(url: RequestInfo | URL) => Promise<Response>>(async () => new Response(JSON.stringify({
      asOf: null, recentDays: 3, baselineDays: 20, minRatio: 1.5,
      scannedCount: 3, totalCount: 0, items: [],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    const { result, rerender } = renderHook(
      (query: VolumeSurgeQuery) => useVolumeSurge(query),
      { initialProps: { page: 1, tickers: ['KGH', 'AAPL.US'] } as VolumeSurgeQuery },
    )
    const lastParams = () => new URL(String(fetchMock.mock.calls.at(-1)?.[0]), 'http://localhost').searchParams
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(lastParams().get('tickers')).toBe('KGH,AAPL.US')

    rerender({ page: 1, tickers: ['PKO'] })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(lastParams().get('tickers')).toBe('PKO')
    rerender({ page: 1, tickers: ['PKO'] })
    expect(fetchMock).toHaveBeenCalledTimes(2)

    rerender({ page: 1, tickers: [] })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(lastParams().get('tickers')).toBe('')

    rerender({ page: 1 })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(lastParams().has('tickers')).toBe(false)
  })
})
