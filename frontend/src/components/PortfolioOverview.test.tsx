import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
  dayChange: { since: '2026-11-11', amount: -50, percent: -4, partial: false },
  weekChange: { since: '2026-11-05', amount: 200, percent: 20, partial: false },
  currencyTotals: [{ currency: 'PLN', marketValue: 1_200, missingQuotes: 0 }],
  missingHoldings: [],
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

  it('shows available values and chart points alongside the holdings missing prices', () => {
    const partial = { ...current, missingQuotes: 2, missingRates: ['USD'] }
    render(<MemoryRouter><PortfolioOverview walletCount={2} summary={{
      ...summary,
      current: partial,
      history: [summary.history[2], partial],
      dayChange: { since: '2026-11-11', amount: -50, percent: -4, partial: true },
      currencyTotals: [
        { currency: 'PLN', marketValue: 1_200, missingQuotes: 1 },
        { currency: 'USD', marketValue: 100, missingQuotes: 1 },
      ],
      missingHoldings: [
        { ticker: 'pko', walletId: 'wallet-a', walletName: 'Retirement', currency: 'PLN' },
        { ticker: 'nvda.us', walletId: 'wallet-b', walletName: 'Savings', currency: 'USD' },
      ],
    }} /></MemoryRouter>)

    expect(screen.getByText('Available holdings value')).toBeVisible()
    expect(screen.getByText('1,200.00 PLN', { selector: 'dd' })).toBeVisible()
    expect(screen.getByText('Missing prices for 2 holdings.')).toBeVisible()
    expect(screen.getByRole('link', { name: 'PKO' })).toHaveAttribute('href', '/stock/pko')
    expect(screen.getByRole('link', { name: 'NVDA.US' })).toHaveAttribute('href', '/stock/nvda.us')
    expect(screen.getByText('· Retirement · PLN')).toBeVisible()
    expect(screen.getByText('· Savings · USD')).toBeVisible()
    expect(screen.getByText('Missing exchange rates for USD.')).toBeVisible()
    expect(screen.getByText('Comparable holdings only')).toBeVisible()
    expect(screen.getByText(/Coverage can vary by day/)).toBeVisible()
    expect(chart.setData).toHaveBeenCalledWith([
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
