// Component test for the Dashboard's market overview. The data hook is mocked,
// so the test drives rendering directly. Covers: the verdict split and its
// counts, both movers lists, the empty-movers wording, that a failed request or
// an empty market renders nothing (the ranking below must not depend on it),
// and that a pooled list names each mover's market.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, within } from '../test/utils'
import type { ApiMarketOverview, ApiRatingMover } from '../api/stocksApi'

const { useMarketOverviewMock } = vi.hoisted(() => ({
  useMarketOverviewMock: vi.fn(),
}))

vi.mock('../hooks/useMarketOverview', () => ({
  useMarketOverview: useMarketOverviewMock,
}))

import { MarketOverview } from './MarketOverview'

function mover(overrides: Partial<ApiRatingMover>): ApiRatingMover {
  return {
    ticker: 'KGH',
    name: 'KGHM',
    market: 'gpw',
    currency: 'PLN',
    lastSession: '2026-09-24',
    lastPrice: 100,
    priceChangePct: 1,
    previousRating: 50,
    currentRating: 64,
    ratingChange: 14,
    lastSignal: 'Buy',
    ...overrides,
  }
}

const OVERVIEW: ApiMarketOverview = {
  asOf: '2026-09-24',
  market: 'gpw',
  breadth: {
    total: 100,
    strongBuy: 5,
    buy: 20,
    hold: 55,
    sell: 15,
    strongSell: 5,
    bullishPct: 25,
    bearishPct: 20,
    averageRating: 51.3,
    advancers: 48,
    decliners: 40,
    unchanged: 12,
    ratingUp: 31,
    ratingDown: 22,
    new52wHighs: 3,
    new52wLows: 0,
  },
  moversUp: [mover({}), mover({ ticker: 'PKN', name: 'Orlen', ratingChange: 9, previousRating: 41, currentRating: 50 })],
  moversDown: [mover({ ticker: 'PKO', name: 'PKO BP', ratingChange: -11, previousRating: 60, currentRating: 49 })],
}

function state(data: ApiMarketOverview | null, extra = {}) {
  useMarketOverviewMock.mockReturnValue({ data, loading: false, error: null, ...extra })
}

beforeEach(() => {
  useMarketOverviewMock.mockReset()
})

describe('MarketOverview', () => {
  it('shows the verdict split with every count', () => {
    state(OVERVIEW)
    renderWithProviders(<MarketOverview market="gpw" />)

    expect(screen.getByRole('img', { name: /25% of stocks are Buy or Strong Buy/i })).toBeInTheDocument()
    expect(screen.getByText('25% bullish')).toBeInTheDocument()
    expect(screen.getByText('20% bearish')).toBeInTheDocument()
    // The five legend counts are text, not only bar widths.
    const legend = screen.getByText('Strong Buy').closest('dl')!
    expect(within(legend).getByText('55')).toBeInTheDocument()
    expect(screen.getByText('51.3')).toBeInTheDocument()
  })

  it('lists the risers and the fallers with the rating before and after', () => {
    state(OVERVIEW)
    renderWithProviders(<MarketOverview market="gpw" />)

    expect(screen.getByText('KGH')).toBeInTheDocument()
    expect(screen.getByText('Orlen')).toBeInTheDocument()
    expect(screen.getByText('PKO')).toBeInTheDocument()
    expect(screen.getByText('+14')).toBeInTheDocument()
    expect(screen.getByText('-11')).toBeInTheDocument()
    // Links go to the stock's own page.
    expect(screen.getByRole('link', { name: 'KGH' })).toHaveAttribute('href', '/stock/kgh')
  })

  it('says so when nobody changed rating', () => {
    state({ ...OVERVIEW, moversUp: [], moversDown: [] })
    renderWithProviders(<MarketOverview market="gpw" />)
    expect(screen.getAllByText(/No stock changed its rating/i)).toHaveLength(2)
  })

  it('renders nothing on a failed request, so the ranking is unaffected', () => {
    state(null, { error: 'boom' })
    const { container } = renderWithProviders(<MarketOverview market="gpw" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for a market with no ranked stocks', () => {
    state({ ...OVERVIEW, breadth: { ...OVERVIEW.breadth, total: 0 } })
    const { container } = renderWithProviders(<MarketOverview market="gpw" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('names the market of each mover when markets are pooled', () => {
    state({
      ...OVERVIEW,
      market: 'all',
      moversUp: [mover({ ticker: 'AAPL.US', name: 'Apple', market: 'us' })],
      moversDown: [],
    })
    renderWithProviders(<MarketOverview market="all" />)
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('US')).toBeInTheDocument()
  })
})
