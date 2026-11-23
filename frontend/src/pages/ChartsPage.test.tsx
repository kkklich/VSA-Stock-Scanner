// Component test for the stock-detail page's VSA Rating card, specifically its
// weekly (multi-timeframe) section. The data hook is mocked so the three states
// the backend can send — the weekly confirms the daily call, it contradicts it,
// or the stock has too little history for a weekly read at all — are driven
// directly, without any network.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Link } from 'react-router-dom'
import { fireEvent, renderWithProviders, screen } from '../test/utils'
import i18n from '../i18n'
import en from '../i18n/locales/en.json'
import type { ApiStockSignals } from '../api/stocksApi'
import { stockTradeMarkers, type StockTradeMarker } from '../lib/stockTradeMarkers'
import type { StockTrade } from '../api/portfoliosApi'
import type { VisibleSpan } from '../components/StockChart'

const { useStockDetailMock, useStockHoldingsMock } = vi.hoisted(() => ({
  useStockDetailMock: vi.fn(),
  useStockHoldingsMock: vi.fn(),
}))

vi.mock('../hooks/useStockDetail', () => ({
  useStockDetail: useStockDetailMock,
}))
vi.mock('../hooks/useStockHoldings', () => ({
  useStockHoldings: useStockHoldingsMock,
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
  StockChart: ({ tradeMarkers, onSpanSettled }: {
    tradeMarkers?: StockTradeMarker[]
    onSpanSettled?: (span: VisibleSpan) => void
  }) => (
    <div data-testid="chart">
      <button onClick={() => onSpanSettled?.({ barsBefore: 20, visibleBars: 50, totalBars: 500 })}>Simulate chart zoom</button>
      <button onClick={() => onSpanSettled?.({ barsBefore: -20, visibleBars: 500, totalBars: 500 })}>Simulate older history</button>
      {tradeMarkers?.map(marker => <span key={`${marker.date}:${marker.side}`}>{marker.label}</span>)}
    </div>
  ),
}))
vi.mock('../components/StockHoldingsCard', () => ({
  StockHoldingsCard: ({ quote }: { quote: ApiStockSignals | null }) => (
    <div data-testid="holdings">{quote?.lastPrice}</div>
  ),
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
import App from '../App'
import { ChartsPage } from './ChartsPage'

const rating = en.chart.rating

beforeEach(() => {
  useStockHoldingsMock.mockReturnValue({ owner: undefined, holdings: null, retry: vi.fn() })
})

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

it('updates the browser tab when opening and leaving stock pages', () => {
  mockData({ ticker: 'VRC', name: 'Vercom S.A.' })
  const routes = () => (
    <>
      <Link to="/stock/kgh">Open KGH</Link>
      <Link to="/legal">Leave stock page</Link>
      <App />
    </>
  )
  const { rerender } = renderWithProviders(routes(), { initialEntries: ['/stock/vrc'] })
  expect(document.title).toBe('Vercom')

  fireEvent.click(screen.getByRole('link', { name: 'Open KGH' }))
  expect(document.title).toBe('KGH')

  mockData()
  rerender(routes())
  expect(document.title).toBe('KGHM Polska Miedz')

  fireEvent.click(screen.getByRole('link', { name: 'Leave stock page' }))
  expect(document.title).toBe('StockPilot')
})

it('opens the existing Constellation Software chart from its Toronto ticker', () => {
  mockData({ ticker: 'CSU.US', name: 'Constellation Software Inc.', currency: 'CAD' })
  renderWithProviders(<App />, { initialEntries: ['/stock/CSU.TO'] })

  expect(useStockDetailMock).toHaveBeenCalledWith('csu.us', expect.any(String), '1d')
  expect(document.title).toBe('Constellation Software Inc.')
})

it('places holdings directly below the observation journal and lets the owner toggle trade markers', async () => {
  await i18n.changeLanguage('en')
  mockData({ lastPrice: 124 })
  useStockHoldingsMock.mockReturnValue({
    owner: 12,
    holdings: {
      quantity: 3,
      wallets: [{
        trades: [{
          side: 'sell', date: '2026-09-08', price: '120', realizedPnl: 25, currency: 'PLN',
        }, {
          side: 'buy', date: '2026-09-07', price: '100', realizedPnl: null, currency: 'PLN',
        }],
      }],
    },
    retry: vi.fn(),
  })
  renderWithProviders(<ChartsPage />)
  const chart = screen.getByTestId('chart')
  const holdings = screen.getByTestId('holdings')
  const journalToggle = screen.getByRole('button', { name: en.journal.title })
  expect(holdings.previousElementSibling).toContainElement(journalToggle)
  expect(holdings).toHaveTextContent('124')
  expect(chart).toHaveTextContent('My sell · 120.00 PLN · +25.00 PLN')
  expect(chart).not.toHaveTextContent('My buy')
  fireEvent.click(screen.getByRole('button', { name: /My trades/ }))
  expect(chart).not.toHaveTextContent('My sell')
})

it('maps trades to weekly candles and only uses known times on intraday charts', () => {
  const purchase: StockTrade = {
    id: 'buy', side: 'buy', date: '2026-09-08', executedAt: null, quantity: '1', price: '100',
    currency: 'PLN', fees: '0', remainingQuantity: null, costBasis: null,
    realizedPnl: null, realizedCostBasis: null,
  }
  const sale: StockTrade = {
    ...purchase, id: 'sell', side: 'sell', executedAt: '2026-09-08T11:35:00Z',
  }
  const candle = makeSignals().history[0]
  const label = (trades: StockTrade[]) => trades[0].id

  expect(stockTradeMarkers([purchase, sale], [{ ...candle, time: '2026-09-11' }], '1w', undefined, label))
    .toEqual([
      { date: '2026-09-11', side: 'buy', label: 'buy' },
      { date: '2026-09-11', side: 'sell', label: 'sell' },
    ])
  const intraday = [
    { ...candle, time: '2026-09-08T13:00:00+02:00' },
    { ...candle, time: '2026-09-08T13:30:00+02:00' },
  ]
  expect(stockTradeMarkers([purchase, sale], intraday, '30m', undefined, label))
    .toEqual([{ date: intraday[1].time, side: 'sell', label: 'sell' }])
})

it('collapses and reopens the three stock sections independently', async () => {
  await i18n.changeLanguage('en')
  mockData()
  renderWithProviders(<App />, { initialEntries: ['/stock/kgh'] })

  const sections = [
    { title: en.insider.title, control: 'checkbox', name: en.insider.includeAllToggle },
    { title: en.chart.simulation.title, control: 'group', name: en.chart.simulation.sidesLabel },
    { title: en.journal.title, control: 'link', name: en.journal.allEntries },
  ].map(({ title, control, name }) => {
    const toggle = screen.getByRole('button', { name: title })
    const content = document.getElementById(toggle.getAttribute('aria-controls')!)
    return { toggle, content, control, name }
  })

  for (const { toggle, content, control, name } of sections) {
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(content).toBeVisible()
    expect(screen.getByRole(control, { name })).toBeVisible()
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toBeVisible()
    expect(content).not.toBeVisible()
    expect(screen.queryByRole(control, { name })).not.toBeInTheDocument()
  }

  for (const { toggle, content, control, name } of sections) {
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(content).toBeVisible()
    expect(screen.getByRole(control, { name })).toBeVisible()
  }
})

describe('ChartsPage history navigation', () => {
  it('keeps older history loaded when zooming in, and still allows explicit shorter ranges', () => {
    mockData()
    renderWithProviders(<ChartsPage />)
    fireEvent.click(screen.getByRole('button', { name: '2Y', exact: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Simulate chart zoom' }))
    expect(screen.getByRole('button', { name: '2Y', exact: true })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: '3M', exact: true }))
    expect(screen.getByRole('button', { name: '3M', exact: true })).toHaveAttribute('aria-pressed', 'true')
  })

  it('loads a wider range when panning beyond the oldest candle', () => {
    mockData()
    renderWithProviders(<ChartsPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Simulate older history' }))
    expect(screen.getByRole('button', { name: '2Y', exact: true })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('ChartsPage - weekly section of the VSA Rating card', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
  })

  it('shows the weekly rating, verdict and a confirming read', () => {
    mockData({
      weeklyRating: 63,
      weeklySignal: 'Buy',
      weeklyAgreement: 'confirms',
    })
    renderWithProviders(<ChartsPage />)

    expect(screen.getByText(rating.weekly)).toBeInTheDocument()
    expect(screen.getByText('63')).toBeInTheDocument()
    expect(screen.getByText('Buy')).toBeInTheDocument()
    expect(screen.getByText(rating.agreement.confirms)).toBeInTheDocument()
  })

  it('warns when the weekly contradicts the daily signal', () => {
    mockData({
      weeklyRating: 25,
      weeklySignal: 'Sell',
      weeklyAgreement: 'conflicts',
    })
    renderWithProviders(<ChartsPage />)

    expect(screen.getByText(rating.agreement.conflicts)).toBeInTheDocument()
    // The daily rating it qualifies is still on screen and unchanged.
    expect(screen.getByText('85')).toBeInTheDocument()
  })

  it('says so plainly when there is not enough history for a weekly read', () => {
    // The backend sends all three fields as null below ~30 weekly bars — a
    // number invented from a handful of weekly candles would be worse than
    // none, so the card must say why it is empty rather than print a 0 or 50.
    mockData()
    renderWithProviders(<ChartsPage />)

    expect(screen.getByText(rating.weeklyUnavailable)).toBeInTheDocument()
    expect(screen.queryByText(rating.agreement.neutral)).not.toBeInTheDocument()
  })
})

// Keep the archived view covered for deliberate reactivation.
vi.mock("../lib/methodStatus", async (importOriginal) => ({
  ...await importOriginal<typeof import("../lib/methodStatus")>(),
  CLASSIC_VSA_ENABLED: true,
}))
