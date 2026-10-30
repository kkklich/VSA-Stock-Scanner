// Component test for the stock-detail page's VSA Rating card, specifically its
// weekly (multi-timeframe) section. The data hook is mocked so the three states
// the backend can send — the weekly confirms the daily call, it contradicts it,
// or the stock has too little history for a weekly read at all — are driven
// directly, without any network.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import i18n from '../i18n'
import en from '../i18n/locales/en.json'
import type { ApiStockSignals } from '../api/stocksApi'

const { useStockDetailMock } = vi.hoisted(() => ({
  useStockDetailMock: vi.fn(),
}))

vi.mock('../hooks/useStockDetail', () => ({
  useStockDetail: useStockDetailMock,
}))

vi.mock('../hooks/useMethods', () => ({
  useMethods: () => ({ methods: [], loading: false, error: null }),
}))

vi.mock('../hooks/useFundamentals', () => ({
  useFundamentals: () => ({ data: null, loading: false }),
}))

vi.mock('../hooks/useTickerVolume', () => ({
  useTickerVolume: () => ({ data: null, loading: false }),
}))

// The chart needs a real canvas, and the sibling cards each fetch on their own —
// none of that is what this test is about.
vi.mock('../components/StockChart', () => ({
  StockChart: () => <div data-testid="chart" />,
}))
vi.mock('../components/AnalyticsSummaryCard', () => ({
  AnalyticsSummaryCard: () => null,
}))
vi.mock('../components/RatingHistoryCard', () => ({
  RatingHistoryCard: () => null,
}))
vi.mock('../components/AiAnalysisCard', () => ({ AiAnalysisCard: () => null }))
vi.mock('../components/TrustScoreCard', () => ({ TrustScoreCard: () => null }))

// Import after the mocks are registered.
import { ChartsPage } from './ChartsPage'

const rating = en.chart.rating

function makeSignals(over: Partial<ApiStockSignals> = {}): ApiStockSignals {
  return {
    ticker: 'KGH',
    name: 'KGHM Polska Miedz',
    sector: 'Mining',
    lastPrice: 123.45,
    priceChangePct: 1.2,
    currentRating: 85,
    ratingChange: 3,
    history: [
      {
        time: '2026-09-08',
        open: 120,
        high: 125,
        low: 119,
        close: 123.45,
        volume: 100000,
      },
    ],
    vsaSignals: [],
    methodSignals: [],
    interval: '1d',
    intraday: false,
    historyStart: '2026-09-08',
    weeklyRating: null,
    weeklySignal: null,
    weeklyAgreement: null,
    ...over,
  }
}

function mockData(over: Partial<ApiStockSignals> = {}) {
  useStockDetailMock.mockReturnValue({
    data: makeSignals(over),
    loading: false,
    error: null,
    noDataForInterval: false,
  })
}

beforeEach(() => { void i18n.changeLanguage('en') })

describe('inactive VSA views', () => {
  it('does not mount classic rating, weekly read, sensitivity or checklist panels', () => {
    mockData()
    renderWithProviders(<ChartsPage />)
    expect(screen.getByTestId('chart')).toBeInTheDocument()
    expect(screen.queryByText(rating.weeklyUnavailable)).not.toBeInTheDocument()
    expect(screen.queryByText(rating.title)).not.toBeInTheDocument()
    expect(screen.queryByText('VSA 85')).not.toBeInTheDocument()
  })
})
