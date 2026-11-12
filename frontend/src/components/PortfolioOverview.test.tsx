import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PortfolioSummary } from '../api/portfoliosApi'
import { PortfolioOverview } from './PortfolioOverview'

const chart = vi.hoisted(() => ({
  create: vi.fn(),
  addSeries: vi.fn(),
  setData: vi.fn(),
  timeScale: vi.fn(),
  fitContent: vi.fn(),
  subscribeCrosshairMove: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('lightweight-charts', () => ({
  createChart: chart.create,
  AreaSeries: {},
  ColorType: { Solid: 'solid' },
  isBusinessDay: () => false,
}))

const current = { date: '2026-11-12', value: 1_200, missingQuotes: 0, staleQuotes: 0, missingRates: [] }
const summary: PortfolioSummary = {
  currency: 'PLN',
  current,
  history: [
    { ...current, date: '2026-11-05', value: 1_000 },
    { ...current, date: '2026-11-06', value: null, missingQuotes: 1 },
    { ...current, date: '2026-11-11', value: 1_250 },
    current,
  ],
  dayChange: { since: '2026-11-11', amount: -50, percent: -4 },
  weekChange: { since: '2026-11-05', amount: 200, percent: 20 },
  currencyTotals: [{ currency: 'PLN', marketValue: 1_200, missingQuotes: 0 }],
}

beforeEach(() => {
  vi.clearAllMocks()
  chart.create.mockReturnValue(chart)
  chart.addSeries.mockReturnValue(chart)
  chart.timeScale.mockReturnValue(chart)
})

describe('PortfolioOverview', () => {
  it('shows value and signed changes and leaves a gap for an unavailable daily value', () => {
    render(<PortfolioOverview summary={summary} walletCount={2} />)

    const section = screen.getByRole('region', { name: 'All wallets' })
    expect(section).toHaveTextContent('2 wallets')
    expect(section).toHaveTextContent('1,200.00 PLN')
    expect(section).toHaveTextContent('-50.00 PLN')
    expect(section).toHaveTextContent('(-4.00%)')
    expect(section).toHaveTextContent('+200.00 PLN')
    expect(section).toHaveTextContent('(+20.00%)')
    expect(chart.setData).toHaveBeenNthCalledWith(1, [
      { time: '2026-11-05', value: 1_000 },
      { time: '2026-11-06' },
      { time: '2026-11-11' },
      { time: '2026-11-12' },
    ])
    expect(chart.setData).toHaveBeenNthCalledWith(2, [
      { time: '2026-11-11', value: 1_250 },
      { time: '2026-11-12', value: 1_200 },
    ])
  })

  it('shows native subtotals when conversion is unavailable', () => {
    const missingRate = { ...current, value: null, missingRates: ['USD'] }
    render(<PortfolioOverview walletCount={2} summary={{
      ...summary,
      current: missingRate,
      history: [missingRate],
      dayChange: null,
      weekChange: null,
      currencyTotals: [
        { currency: 'PLN', marketValue: 900, missingQuotes: 0 },
        { currency: 'USD', marketValue: 100, missingQuotes: 0 },
      ],
    }} />)

    const section = screen.getByRole('region', { name: 'All wallets' })
    expect(section).toHaveTextContent('Combined value unavailable')
    expect(section).toHaveTextContent('Missing exchange rates for USD.')
    expect(section).toHaveTextContent('100.00')
    expect(chart.create).not.toHaveBeenCalled()
  })
})
