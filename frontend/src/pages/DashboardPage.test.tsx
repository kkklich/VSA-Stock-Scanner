// Component test for the ranking table on the Dashboard. The data hook is
// mocked so the test drives the table's rendering + interactions directly,
// without any network. Covers: rows render, loading/error/empty states, the
// footer count, and that a column header re-sorts via the data hook's params.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../test/utils'
import type { ApiRankingItem } from '../api/stocksApi'
import type { UseInfiniteRankingResult } from '../hooks/useRanking'

const { useInfiniteRankingMock } = vi.hoisted(() => ({
  useInfiniteRankingMock: vi.fn(),
}))

vi.mock('../hooks/useRanking', () => ({
  useInfiniteRanking: useInfiniteRankingMock,
}))

vi.mock('../hooks/useMethods', () => ({
  useMethods: () => ({
    methods: [
      {
        id: 'vsa',
        name: 'VSA Rating',
        description: 'Volume Spread Analysis',
        source: 'Tom Williams',
        sourceUrl: null,
        direction: 'Bullish',
      },
    ],
    loading: false,
    error: null,
  }),
}))

// The Refresh button pulls fresh data over the network — stub it out.
vi.mock('../components/RefreshButton', () => ({
  RefreshButton: () => <button type="button">Refresh</button>,
}))

// Import after the mocks are registered.
import { DashboardPage } from './DashboardPage'

function makeRow(over: Partial<ApiRankingItem> = {}): ApiRankingItem {
  return {
    ticker: 'KGH',
    name: 'KGHM Polska Miedz',
    lastPrice: 123.45,
    priceChangePct: 1.2,
    currentRating: 72,
    ratingChange: 3,
    lastSignal: 'Buy',
    daysSinceSignal: 2,
    sparkline: [1, 2, 3, 4, 5],
    volume: 100000,
    sector: 'Mining',
    aiConfidence: 60,
    distFrom52wHighPct: -5,
    distFrom52wLowPct: 20,
    isNew52wHigh: false,
    isNew52wLow: false,
    methodResults: {
      vsa: {
        methodId: 'vsa',
        score: 72,
        daysSince: 2,
        fired: true,
        detail: 'Buy',
        available: true,
      },
    },
    combinedScore: 72,
    weeklyRating: null,
    weeklySignal: null,
    weeklyAgreement: null,
    ...over,
  }
}

const ROWS: ApiRankingItem[] = [
  makeRow({ ticker: 'KGH', name: 'KGHM Polska Miedz', combinedScore: 72 }),
  makeRow({ ticker: 'PKN', name: 'PKN Orlen', combinedScore: 55 }),
]

function result(over: Partial<UseInfiniteRankingResult> = {}): UseInfiniteRankingResult {
  return {
    items: ROWS,
    total: ROWS.length,
    loading: false,
    loadingMore: false,
    hasMore: false,
    error: null,
    loadMore: vi.fn(),
    refetch: vi.fn(),
    ...over,
  }
}

beforeEach(() => {
  useInfiniteRankingMock.mockReturnValue(result())
})

describe('DashboardPage ranking table', () => {
  it('renders the heading and one row per stock', () => {
    renderWithProviders(<DashboardPage />)
    expect(
      screen.getByRole('heading', { name: /Best stocks today/i }),
    ).toBeInTheDocument()
    // Each company name appears in both the desktop table and the mobile card.
    expect(screen.getAllByText('KGHM Polska Miedz').length).toBeGreaterThan(0)
    expect(screen.getAllByText('PKN Orlen').length).toBeGreaterThan(0)
    expect(screen.getByText(/Showing 2 of 2 stocks/i)).toBeInTheDocument()
  })

  it('shows the loading state while the first page loads', () => {
    useInfiniteRankingMock.mockReturnValue(result({ items: null, loading: true }))
    renderWithProviders(<DashboardPage />)
    expect(screen.getByText(/Loading GPW rankings/i)).toBeInTheDocument()
  })

  it('shows a backend error with a retry action', () => {
    useInfiniteRankingMock.mockReturnValue(
      result({ items: null, error: 'boom' }),
    )
    renderWithProviders(<DashboardPage />)
    expect(screen.getByText(/Backend error/i)).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
  })

  it('shows the empty state when nothing matches', () => {
    useInfiniteRankingMock.mockReturnValue(result({ items: [], total: 0 }))
    renderWithProviders(<DashboardPage />)
    expect(
      screen.getByText(/No stocks match your search or filters/i),
    ).toBeInTheDocument()
  })

  it('flags weekly agreement next to the daily signal', () => {
    useInfiniteRankingMock.mockReturnValue(
      result({
        items: [
          makeRow({
            ticker: 'KGH',
            weeklyAgreement: 'confirms',
            weeklyRating: 78,
            weeklySignal: 'Buy',
          }),
          makeRow({
            ticker: 'PKN',
            weeklyAgreement: 'conflicts',
            weeklyRating: 22,
            weeklySignal: 'Sell',
          }),
        ],
        total: 2,
      }),
    )
    renderWithProviders(<DashboardPage />)
    // Rendered in both the desktop table and the mobile card list.
    expect(screen.getAllByText(/1W ✓/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/1W ✗/).length).toBeGreaterThan(0)
  })

  it('shows no weekly chip when the weekly read is neutral or unavailable', () => {
    useInfiniteRankingMock.mockReturnValue(
      result({
        items: [
          makeRow({ ticker: 'KGH', weeklyAgreement: 'neutral', weeklyRating: 50 }),
          makeRow({ ticker: 'PKN' }), // no weekly reading at all
        ],
        total: 2,
      }),
    )
    renderWithProviders(<DashboardPage />)
    expect(screen.queryByText(/1W ✓/)).not.toBeInTheDocument()
    expect(screen.queryByText(/1W ✗/)).not.toBeInTheDocument()
  })

  it('re-sorts through the data hook when a column header is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DashboardPage />)

    // Default sort is the combined cross-method score, descending.
    expect(useInfiniteRankingMock.mock.calls.at(-1)?.[0]).toMatchObject({
      sortBy: 'combinedScore',
      sortDir: 'desc',
    })

    await user.click(screen.getByRole('button', { name: 'Sort by Symbol' }))

    // The last render requested a ticker-sorted page (ascending for a label col).
    expect(useInfiniteRankingMock.mock.calls.at(-1)?.[0]).toMatchObject({
      sortBy: 'ticker',
      sortDir: 'asc',
    })
  })
})
