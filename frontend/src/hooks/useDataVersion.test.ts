// The app-wide "has the data changed?" watcher: the first answer is only a
// baseline, a later different one bumps the version, and a caller that
// reloads its own data (the Refresh button) can say so without a second
// reload happening.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import type { ApiRefreshStatus } from '../api/stocksApi'

const api = vi.hoisted(() => ({ fetchRefreshStatus: vi.fn() }))
vi.mock('../api/stocksApi', () => ({ fetchRefreshStatus: api.fetchRefreshStatus }))

import {
  noteRefreshStatus,
  resetDataVersionForTests,
  useDataVersion,
  useLiveMarketTimes,
} from './useDataVersion'

function status(overrides: Partial<ApiRefreshStatus> = {}): ApiRefreshStatus {
  return {
    state: 'idle',
    lastStartedAt: null,
    lastRefreshAt: '2026-09-24T16:04:00Z',
    lastError: null,
    stocksRanked: 130,
    dbEnabled: true,
    livePricesAt: '2026-09-25T09:00:20Z',
    liveMarkets: { gpw: '2026-09-25T09:00:20Z' },
    ...overrides,
  }
}

afterEach(() => {
  resetDataVersionForTests()
  vi.useRealTimers()
})

describe('noteRefreshStatus', () => {
  it('takes the first status as the baseline, and bumps on a change', () => {
    api.fetchRefreshStatus.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useDataVersion())
    expect(result.current).toBe(0)

    act(() => noteRefreshStatus(status()))
    expect(result.current).toBe(0)

    // The same data again: nothing to reload.
    act(() => noteRefreshStatus(status()))
    expect(result.current).toBe(0)

    // The 12:00 live-price run replaced today's prices.
    act(() => noteRefreshStatus(status({ livePricesAt: '2026-09-25T10:00:18Z' })))
    expect(result.current).toBe(1)

    // The evening refresh stored the day's final bars.
    act(() =>
      noteRefreshStatus(
        status({ livePricesAt: '2026-09-25T10:00:18Z', lastRefreshAt: '2026-09-25T16:03:00Z' }),
      ),
    )
    expect(result.current).toBe(2)
  })

  it('lets a caller that reloads by itself note a change without a bump', () => {
    api.fetchRefreshStatus.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useDataVersion())
    act(() => noteRefreshStatus(status()))
    act(() =>
      noteRefreshStatus(status({ lastRefreshAt: '2026-09-25T12:30:00Z' }), { bump: false }),
    )
    expect(result.current).toBe(0)
    // ...and that change is now the baseline, not news.
    act(() => noteRefreshStatus(status({ lastRefreshAt: '2026-09-25T12:30:00Z' })))
    expect(result.current).toBe(0)
  })

  it('publishes when each market was last downloaded', () => {
    api.fetchRefreshStatus.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useLiveMarketTimes())
    expect(result.current).toEqual({})
    act(() => noteRefreshStatus(status()))
    expect(result.current).toEqual({ gpw: '2026-09-25T09:00:20Z' })
  })
})

describe('the watcher', () => {
  it('asks at once, then again on its interval, and bumps on news', async () => {
    vi.useFakeTimers()
    api.fetchRefreshStatus.mockResolvedValueOnce(status())
    const { result } = renderHook(() => useDataVersion())
    await act(async () => {
      await Promise.resolve()
    })
    expect(api.fetchRefreshStatus).toHaveBeenCalledTimes(1)
    expect(result.current).toBe(0)

    api.fetchRefreshStatus.mockResolvedValueOnce(
      status({ livePricesAt: '2026-09-25T10:00:18Z' }),
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000)
    })
    expect(api.fetchRefreshStatus).toHaveBeenCalledTimes(2)
    expect(result.current).toBe(1)
  })

  it('takes its baseline even in a background tab, then waits until the tab is shown', async () => {
    vi.useFakeTimers()
    const visibility = vi
      .spyOn(Document.prototype, 'visibilityState', 'get')
      .mockReturnValue('hidden')
    const flush = async () => {
      for (let i = 0; i < 5; i += 1) await Promise.resolve()
    }
    api.fetchRefreshStatus.mockResolvedValue(status())
    const { result } = renderHook(() => useDataVersion())
    await act(flush)
    // The baseline is taken although the tab is hidden: it is what the page's
    // own data was loaded against.
    expect(api.fetchRefreshStatus).toHaveBeenCalledTimes(1)

    // The periodic asks wait while the tab stays in the background.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000)
    })
    expect(api.fetchRefreshStatus).toHaveBeenCalledTimes(1)

    // Brought to the front after the 14:00 run: it asks at once and reloads.
    api.fetchRefreshStatus.mockResolvedValue(status({ livePricesAt: '2026-09-25T12:00:18Z' }))
    visibility.mockReturnValue('visible')
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await flush()
    })
    expect(api.fetchRefreshStatus).toHaveBeenCalledTimes(2)
    expect(result.current).toBe(1)
  })

  it('keeps quiet when the status cannot be read', async () => {
    api.fetchRefreshStatus.mockRejectedValue(new Error('offline'))
    const { result } = renderHook(() => useDataVersion())
    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current).toBe(0)
  })
})
