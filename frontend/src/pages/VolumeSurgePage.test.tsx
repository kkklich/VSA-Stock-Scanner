// Component test for the Volume surge page's surge context (roadmap #15b):
// the report chip, the peak-day reading, the range tag and the signal age.
// The data hooks are mocked, so nothing goes over the network.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { act, renderWithProviders, screen, within } from '../test/utils'
import type { ApiVolumeSurgeItem, ApiVolumeSurgeResponse } from '../api/stocksApi'
import { FAVORITES_KEY, saveFavorites } from '../lib/favorites'
import { WatchlistsContext, useWatchlists } from '../hooks/useWatchlists'

const { useVolumeSurgeMock } = vi.hoisted(() => ({ useVolumeSurgeMock: vi.fn() }))

vi.mock('../hooks/useVolumeSurge', () => ({ useVolumeSurge: useVolumeSurgeMock }))
vi.mock('../hooks/useMarkets', () => ({
  useMarketScope: () => ({ market: 'gpw', markets: null }),
}))

import { VolumeSurgePage } from './VolumeSurgePage'

function makeItem(over: Partial<ApiVolumeSurgeItem> = {}): ApiVolumeSurgeItem {
  return {
    ticker: 'KGH',
    name: 'KGHM Polska Miedz',
    sector: 'Mining',
    market: 'gpw',
    currency: 'PLN',
    lastPrice: 150,
    recentAvgVolume: 300_000,
    baselineAvgVolume: 100_000,
    volumeRatio: 3,
    lastDayRatio: 3,
    daysAboveBaseline: 3,
    priceChangePct: 4.5,
    currentRating: 70,
    lastSignal: 'Buy',
    daysSinceSignal: 23,
    signalInWindow: false,
    surgeStart: '2026-09-23',
    peakDate: '2026-09-24',
    peakVolumeRatio: 4.2,
    peakChangePct: 3.1,
    peakSpreadRatio: 2,
    peakClosePosition: 0.9,
    breaksHigh: true,
    breaksLow: false,
    reportDate: '2026-09-23',
    ...over,
  }
}

function mockScan(items: ApiVolumeSurgeItem[]) {
  const meta: ApiVolumeSurgeResponse = {
    asOf: '2026-09-25',
    recentDays: 3,
    baselineDays: 20,
    minRatio: 1.5,
    scannedCount: 130,
    totalCount: items.length,
    items,
  }
  useVolumeSurgeMock.mockReturnValue({
    items,
    meta,
    loading: false,
    loadingMore: false,
    error: null,
    hasMore: false,
    refetch: vi.fn(),
  })
}

describe('VolumeSurgePage surge context', () => {
  beforeEach(() => {
    localStorage.clear()
    useVolumeSurgeMock.mockClear()
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
  })

  it('marks a surge that lines up with a report', () => {
    mockScan([makeItem(), makeItem({ ticker: 'PKO', name: 'PKO BP', reportDate: null })])
    renderWithProviders(<VolumeSurgePage />)
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    // Header + two rows; only KGHM carries the chip.
    expect(within(rows[1]).getByText('REPORT')).toBeInTheDocument()
    expect(within(rows[2]).queryByText('REPORT')).toBeNull()
  })

  it('reads the peak session, the range break and the signal age', () => {
    mockScan([makeItem()])
    renderWithProviders(<VolumeSurgePage />)
    const row = within(screen.getByRole('table')).getAllByRole('row')[1]
    expect(within(row).getByText('Thu 24.09')).toBeInTheDocument()
    expect(within(row).getByText(/Wide, closed high/)).toBeInTheDocument()
    expect(within(row).getByText('↑ 20-session high')).toBeInTheDocument()
    expect(within(row).getByText('last signal 23 d ago')).toBeInTheDocument()
  })

  it('says when the signal belongs to the surge', () => {
    mockScan([
      makeItem({ signalInWindow: true, daysSinceSignal: 1, breaksHigh: false }),
    ])
    renderWithProviders(<VolumeSurgePage />)
    const row = within(screen.getByRole('table')).getAllByRole('row')[1]
    expect(within(row).getByText('signal in the surge')).toBeInTheDocument()
    expect(within(row).queryByText(/20-session/)).toBeNull()
  })

  it('explains the typical-session baseline in the header', () => {
    mockScan([makeItem()])
    renderWithProviders(<VolumeSurgePage />)
    expect(screen.getByText(/their typical/)).toBeInTheDocument()
  })

  it('filters by the shared favorites and updates when their membership changes', async () => {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify({ KGH: true, PKO: false }))
    mockScan([makeItem()])
    const user = userEvent.setup()
    renderWithProviders(<VolumeSurgePage />)
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].tickers).toBeUndefined()

    const button = screen.getByRole('button', { name: /Favorites/ })
    await user.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0]).toMatchObject({ tickers: ['KGH'], page: 1 })

    act(() => saveFavorites({ PKO: true }))
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].tickers).toEqual(['PKO'])

    await user.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].tickers).toBeUndefined()
  })

  it('starts from page one when favorites are enabled after scrolling', async () => {
    let intersect: (entries: { isIntersecting: boolean }[]) => void = () => {}
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: typeof intersect) { intersect = callback }
      observe() {}
      disconnect() {}
    })
    localStorage.setItem(FAVORITES_KEY, JSON.stringify({ KGH: true }))
    mockScan(Array.from({ length: 25 }, (_, i) => makeItem({ ticker: `T${i}` })))
    useVolumeSurgeMock.mockReturnValue({ ...useVolumeSurgeMock(), hasMore: true })
    const user = userEvent.setup()
    renderWithProviders(<VolumeSurgePage />)
    act(() => intersect([{ isIntersecting: true }]))
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].page).toBe(2)

    await user.click(screen.getByRole('button', { name: /Favorites/ }))
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0]).toMatchObject({ page: 1, tickers: ['KGH'] })
  })

  it('follows the selected account list instead of browser favorites', async () => {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify({ KGH: true }))
    mockScan([])
    const user = userEvent.setup()
    function AccountList({ ticker }: { ticker: string }) {
      const state = useWatchlists()
      return <WatchlistsContext.Provider value={{ ...state, stars: { [ticker]: true } }}>
        <VolumeSurgePage />
      </WatchlistsContext.Provider>
    }
    const { rerender } = renderWithProviders(<AccountList ticker="PKO" />)
    await user.click(screen.getByRole('button', { name: /Favorites/ }))
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].tickers).toEqual(['PKO'])

    rerender(<AccountList ticker="AAPL.US" />)
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0]).toMatchObject({ page: 1, tickers: ['AAPL.US'] })
  })

  it('distinguishes no favorites from no matching surges and offers the full list', async () => {
    mockScan([])
    const user = userEvent.setup()
    renderWithProviders(<VolumeSurgePage />)
    await user.click(screen.getByRole('button', { name: /Favorites/ }))
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].tickers).toEqual([])
    expect(screen.getByText(/You have not starred any company yet/)).toBeInTheDocument()

    act(() => saveFavorites({ KGH: true }))
    expect(screen.getByText(/None of your favorite companies/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show all companies' }))
    expect(useVolumeSurgeMock.mock.calls.at(-1)?.[0].tickers).toBeUndefined()
    expect(screen.getByText(/No stock currently trades/)).toBeInTheDocument()
  })
})

// Keep the archived view covered for deliberate reactivation.
vi.mock("../lib/methodStatus", async (importOriginal) => ({
  ...await importOriginal<typeof import("../lib/methodStatus")>(),
  CLASSIC_VSA_ENABLED: true,
}))
