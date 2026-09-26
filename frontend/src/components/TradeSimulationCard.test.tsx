// Component test for the VSA V4 trade-simulation card. The data hook is mocked,
// so rendering is driven directly. Covers: the headline statistics, the trade
// list (newest first, "show all"), the long-only / long + short switch reaching
// the hook, the no-setups state, and never showing another stock's result.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, renderWithProviders, screen } from '../test/utils'
import type { ApiSimulatedTrade, ApiTradeSimulation } from '../api/stocksApi'
import type { UseTradeSimulationResult } from '../hooks/useTradeSimulation'

const { useTradeSimulationMock } = vi.hoisted(() => ({
  useTradeSimulationMock: vi.fn(),
}))

vi.mock('../hooks/useTradeSimulation', () => ({
  useTradeSimulation: useTradeSimulationMock,
}))

// Import after the mock is registered.
import { TradeSimulationCard } from './TradeSimulationCard'

function trade(i: number, over: Partial<ApiSimulatedTrade> = {}): ApiSimulatedTrade {
  const day = String(i + 1).padStart(2, '0')
  return {
    status: 'closed',
    direction: 'long',
    signalDate: `2026-03-${day}`,
    entryDate: `2026-03-${day}`,
    exitDate: `2026-04-${day}`,
    setup: i === 6 ? 'Shakeout → Test' : 'Selling Climax → No Supply',
    entryPrice: 100,
    stopLoss: 95,
    takeProfit: 115,
    exitPrice: 115,
    exitReason: 'take_profit',
    quantity: 10,
    netPnl: 290,
    netR: 2.9,
    returnPct: 15,
    ...over,
  }
}

const SIM: ApiTradeSimulation = {
  ticker: 'KGH',
  methodId: 'vsa4',
  currency: 'PLN',
  fromDate: '2021-08-26',
  asOf: '2026-09-24',
  barCount: 1272,
  sides: 'long',
  initialCapital: 10000,
  riskPct: 1,
  rewardRisk: 3,
  commissionPct: 0.2,
  slippagePct: 0.05,
  finalEquity: 10291.87,
  totalReturnPct: 2.92,
  maxDrawdownPct: 6.84,
  closedTrades: 7,
  openTrades: 0,
  wins: 2,
  losses: 5,
  winRatePct: 28.57,
  profitFactor: 1.18,
  avgR: 0.12,
  skippedEntries: 3,
  longSetups: 10,
  shortSetups: 4,
  buyHoldReturnPct: 101.8,
  trades: Array.from({ length: 7 }, (_, i) =>
    i === 3 ? trade(i, { netPnl: -105, netR: -1.05, exitReason: 'stop', exitPrice: 95, returnPct: -5 }) : trade(i),
  ),
  equity: [
    { date: '2021-08-26', equity: 10000, drawdownPct: 0 },
    { date: '2024-01-02', equity: 9800, drawdownPct: 2 },
    { date: '2026-09-24', equity: 10291.87, drawdownPct: 0 },
  ],
  engine: 'vsa-kompendium-program-2026-09-24',
}

function result(over: Partial<UseTradeSimulationResult> = {}): UseTradeSimulationResult {
  return { data: SIM, loading: false, error: null, ...over }
}

beforeEach(() => {
  useTradeSimulationMock.mockReset()
  useTradeSimulationMock.mockReturnValue(result())
})

describe('TradeSimulationCard', () => {
  it('leads with the R statistics and shows buy & hold as context', () => {
    renderWithProviders(<TradeSimulationCard ticker="kgh" />)

    expect(screen.getByText('Trade simulation · VSA V4')).toBeInTheDocument()
    expect(screen.getByText('29%')).toBeInTheDocument() // win rate
    expect(screen.getByText('+0.12R')).toBeInTheDocument() // average R
    expect(screen.getByText('1.18')).toBeInTheDocument() // profit factor
    expect(screen.getByText('+2.92%')).toBeInTheDocument() // account
    expect(screen.getByText('+101.80%')).toBeInTheDocument() // buy & hold
    expect(screen.getByText(/Setups confirmed: 10 long, 4 short/)).toBeInTheDocument()
    expect(screen.getByText(/entries skipped: 3/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Simulated account value/ })).toBeInTheDocument()
    // The assumptions line spells out the costs and the window.
    expect(screen.getByText(/0\.20% \+ 0\.05% slippage/)).toBeInTheDocument()
  })

  it('lists trades newest first, five at a time', () => {
    renderWithProviders(<TradeSimulationCard ticker="kgh" />)

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(5)
    // The newest trade (index 6) comes first.
    expect(items[0]).toHaveTextContent('2026-03-07')
    expect(items[0]).toHaveTextContent('Shakeout → Test')
    expect(screen.getByText('-1.05R')).toBeInTheDocument() // the stopped-out trade

    fireEvent.click(screen.getByRole('button', { name: 'Show all (7)' }))
    expect(screen.getAllByRole('listitem')).toHaveLength(7)
  })

  it('passes the long-only / long + short choice to the hook', () => {
    renderWithProviders(<TradeSimulationCard ticker="kgh" />)
    expect(useTradeSimulationMock).toHaveBeenLastCalledWith('kgh', 'long')

    fireEvent.click(screen.getByRole('button', { name: 'Long + short' }))
    expect(useTradeSimulationMock).toHaveBeenLastCalledWith('kgh', 'both')
    expect(screen.getByRole('button', { name: 'Long + short' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('says so when the sequence never completed', () => {
    useTradeSimulationMock.mockReturnValue(
      result({ data: { ...SIM, longSetups: 0, shortSetups: 0, closedTrades: 0, trades: [] } }),
    )
    renderWithProviders(<TradeSimulationCard ticker="kgh" />)
    expect(screen.getByText(/never completed/)).toBeInTheDocument()
  })

  it("never shows another stock's result while loading", () => {
    useTradeSimulationMock.mockReturnValue(result({ loading: true }))
    renderWithProviders(<TradeSimulationCard ticker="pko" />)
    expect(screen.queryByText('29%')).not.toBeInTheDocument()
    expect(screen.getByText(/Replaying the program/)).toBeInTheDocument()
  })

  it('shows an error message when the fetch fails', () => {
    useTradeSimulationMock.mockReturnValue(result({ data: null, error: 'boom' }))
    renderWithProviders(<TradeSimulationCard ticker="kgh" />)
    expect(screen.getByText(/Simulation unavailable: boom/)).toBeInTheDocument()
  })
})
