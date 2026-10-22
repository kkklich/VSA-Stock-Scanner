import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, within } from '../test/utils'
import i18n from '../i18n'
import type { LongTermItem } from '../types/longTerm'
import { LongTermPage } from './LongTermPage'
import { FAVORITES_KEY } from '../lib/favorites'

const mocks = vi.hoisted(() => ({ ranking: vi.fn(), scores: vi.fn(), financials: vi.fn(), market: vi.fn(), pick: vi.fn() }))
vi.mock('../hooks/useLongTerm', () => ({ useLongTermRanking: mocks.ranking, useLongTermHistory: mocks.scores, useFinancialHistory: mocks.financials }))
vi.mock('../hooks/useMarkets', () => ({ useSingleMarket: mocks.market }))

function item(ticker: string, score: number | null): LongTermItem {
  return { ticker, name: `${ticker.toUpperCase()} Company`, sector: 'Industry', market: 'gpw', currency: 'PLN',
    asOf: '2026-10-21', score, qualityScore: score, valueScore: score, momentumScore: score, coverage: score === null ? 50 : 100,
    eligible: score !== null, missing: score === null ? ['fundamentals_missing'] : [],
    inputs: { roe: 0.12, roa: 0.08, netMargin: 0.1, earningsYield: 0.06, momentum12_1: 0.3, momentum6_1: 0.2 },
    fundamentalsObservedAt: '2026-10-20T12:00:00Z', comparisonGroup: 'market', peerCount: 20 }
}
function result<T>(data: T) { return { data, loading: false, error: false, refetch: vi.fn(), lastUpdated: '2026-10-22T13:00:00Z', stale: false } }
const items = [item('low', 20), item('missing', null), item('high', 90)]
function rows() { return within(screen.getByRole('table')).getAllByRole('row').slice(1) }

beforeEach(() => {
  localStorage.removeItem(FAVORITES_KEY)
  mocks.ranking.mockReturnValue(result({ market: 'gpw', asOf: '2026-10-21', modelVersion: 'qvm-v1', dbEnabled: true, items, totalCount: 3, scoredCount: 2 }))
  mocks.market.mockReturnValue({ market: 'gpw', markets: [{ id: 'gpw', shortName: 'GPW' }, { id: 'us', shortName: 'US' }], needsPicker: true, pick: mocks.pick })
  mocks.scores.mockReturnValue(result({ ticker: 'high', dbEnabled: true, items: [] }))
  mocks.financials.mockReturnValue(result({ ticker: 'high', dbEnabled: true, items: [] }))
  vi.clearAllMocks()
})
afterEach(async () => { await i18n.changeLanguage('en') })

describe('Long-term ranking', () => {
  it('ranks high scores first and leaves missing values last in both directions', async () => {
    renderWithProviders(<LongTermPage />)
    expect(rows().map((row) => within(row).getByRole('link').textContent)).toEqual(['HIGH', 'LOW', 'MISSING'])
    expect(within(rows()[2]).getAllByText('—')).toHaveLength(4)
    expect(screen.getByText('Financial data unavailable')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Descending/ }))
    expect(rows().map((row) => within(row).getByRole('link').textContent)).toEqual(['LOW', 'HIGH', 'MISSING'])
  })

  it('filters by name and switches only to an individual market', async () => {
    renderWithProviders(<LongTermPage />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Search ticker or name' }), 'high company')
    expect(rows()).toHaveLength(1)
    expect(within(rows()[0]).getByRole('link')).toHaveTextContent('HIGH')
    await userEvent.click(screen.getByRole('button', { name: 'US' }))
    expect(mocks.pick).toHaveBeenCalledWith('us')
    expect(screen.queryByRole('button', { name: /All markets/ })).not.toBeInTheDocument()
    expect(mocks.ranking).toHaveBeenCalledWith('gpw')
  })

  it('expands score revisions and financial observations with separate session and report dates', async () => {
    mocks.scores.mockReturnValue(result({ ticker: 'high', dbEnabled: true, items: [
      { ...item('high', 90), recordedAt: '2026-10-22T12:00:00Z', modelVersion: 'qvm-v1' },
      { ...item('high', 80), recordedAt: '2026-10-21T12:00:00Z', modelVersion: 'qvm-v1' },
    ] }))
    mocks.financials.mockReturnValue(result({ ticker: 'high', dbEnabled: true, items: [
      { observedAt: '2026-10-22T10:00:00Z', kind: 'quarterly', source: 'yahoo', payload: { financialCurrency: 'EUR', reports: [{ periodEnd: '2026-06-30', totalRevenue: 100000, netIncome: 20000 }] } },
      { observedAt: '2026-10-20T10:00:00Z', kind: 'fundamentals', source: 'yahoo', payload: { returnOnEquity: 0.12, financialCurrency: 'EUR', peRatio: null } },
    ] }))
    renderWithProviders(<LongTermPage />)
    const toggle = screen.getByRole('button', { name: 'Inputs and history for HIGH' })
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toBeInTheDocument()
    expect(mocks.scores).toHaveBeenCalledWith(null)
    expect(mocks.financials).toHaveBeenCalledWith(null)
    expect(mocks.scores).toHaveBeenCalledTimes(1)
    expect(mocks.financials).toHaveBeenCalledTimes(1)
    expect(screen.getAllByText(/Financial comparison group: market. Momentum compares stocks across the market/)[0]).toBeVisible()
    await userEvent.click(screen.getByRole('tab', { name: 'Score history' }))
    expect(screen.getByText(/not their original publication date/)).toBeInTheDocument()
    expect(mocks.scores).toHaveBeenLastCalledWith('high')
    const scores = screen.getByRole('region', { name: 'Recorded scores' })
    const entries = scores.querySelectorAll('summary')
    expect(entries).toHaveLength(2)
    await userEvent.click(entries[0])
    expect(within(entries[0].parentElement!).getByText(/Market session: 2026-10-21/)).toBeVisible()
    expect(within(scores).getAllByText('30%')[0]).toBeVisible()
    await userEvent.click(screen.getByRole('tab', { name: 'Financial data' }))
    expect(mocks.financials).toHaveBeenLastCalledWith('high')
    const finances = screen.getByRole('region', { name: 'Financial observations' })
    await userEvent.click(finances.querySelector('summary')!)
    expect(within(finances).getByText('Report period end')).toBeVisible()
    expect(within(finances).getByText('2026-06-30')).toBeVisible()
    expect(within(finances).getByText(/Reporting currency at observation: EUR/)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Close details' }))
    expect(screen.queryByRole('region', { name: 'Recorded scores' })).not.toBeInTheDocument()
    expect(toggle).toHaveFocus()
  })

  it('uses only recorded currencies, keeping unknown quote and EPS currencies explicit', async () => {
    mocks.financials.mockReturnValue(result({ ticker: 'high', dbEnabled: true, items: [
      { observedAt: '2026-10-22T10:00:00Z', kind: 'fundamentals', source: 'yahoo', payload: { marketCap: 100000000, eps: 2.5, totalRevenue: 700000, peRatio: 20, financialCurrency: 'USD' } },
      { observedAt: '2026-10-22T10:00:00Z', kind: 'quarterly', source: 'yahoo', payload: { financialCurrency: 'EUR', reports: [{ periodEnd: '2026-06-30', totalRevenue: 100000, eps: 1.25 }] } },
      { observedAt: '2026-10-22T10:00:00Z', kind: 'cashflow', source: 'yahoo', payload: { periods: [{ periodEnd: '2026-06-30', periodType: 'quarterly', operatingCashFlow: 120000, currency: 'GBP' }] } },
    ] }))
    renderWithProviders(<LongTermPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Inputs and history for HIGH' }))
    await userEvent.click(screen.getByRole('tab', { name: 'Financial data' }))
    const finances = screen.getByRole('region', { name: 'Financial observations' })
    for (const summary of finances.querySelectorAll('summary')) await userEvent.click(summary)
    expect(within(finances).getByText('100,000,000 (currency not recorded)')).toBeVisible()
    expect(within(finances).getByText('2.5 (currency not recorded)')).toBeVisible()
    expect(within(finances).getByText('700,000 USD')).toBeVisible()
    expect(within(finances).getByText('100,000 (currency not recorded)')).toBeVisible()
    expect(within(finances).getByText('1.25 (currency not recorded)')).toBeVisible()
    expect(within(finances).getByText(/Reporting currency at observation: EUR/)).toBeVisible()
    expect(within(finances).getByText('120,000 GBP')).toBeVisible()
    expect(within(finances).getByText('20')).toBeVisible()
    expect(within(finances).queryByText(/PLN/)).not.toBeInTheDocument()
  })

  it('explains the zero valuation input for loss-making stocks as a model rule', async () => {
    const loss = { ...item('loss', 10), valueScore: 0, inputs: { ...item('loss', 10).inputs, earningsYield: 0, netMargin: -0.2 } }
    mocks.ranking.mockReturnValue(result({ market: 'gpw', asOf: loss.asOf, modelVersion: 'qvm-v1', dbEnabled: true, items: [loss], totalCount: 1, scoredCount: 1 }))
    renderWithProviders(<LongTermPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Inputs and history for LOSS' }))
    expect(screen.getByText(/scoring rule, not an observed 0% earnings yield/)).toBeVisible()
    expect(screen.getByText('-20%')).toBeVisible()
  })

  it('keeps a short score disclaimer visible and expands the methodology on demand', async () => {
    mocks.ranking.mockReturnValue(result({ market: 'gpw', asOf: null, modelVersion: 'qvm-v1', dbEnabled: false, items: [], totalCount: 0, scoredCount: 0 }))
    renderWithProviders(<LongTermPage />)
    expect(screen.getByText(/database is not configured/)).toBeInTheDocument()
    expect(screen.getByText(/Relative score 0–100/)).toBeVisible()
    expect(screen.getByText(/equal weight/)).not.toBeVisible()
    await userEvent.click(screen.getByText('How scoring works'))
    expect(screen.getByText(/equal weight/)).toBeVisible()
    expect(screen.getByText(/No ranking data yet/)).toBeInTheDocument()
  })

  it('combines scored, sector, watchlist and search filters with a matching count and reset', async () => {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify({ high: true, missing: true }))
    mocks.ranking.mockReturnValue(result({ market: 'gpw', asOf: '2026-10-21', modelVersion: 'qvm-v1', dbEnabled: true,
      items: [{ ...items[0], sector: 'Finance' }, items[1], items[2]], totalCount: 3, scoredCount: 2 }))
    renderWithProviders(<LongTermPage />)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Watchlist only' }))
    expect(rows()).toHaveLength(2)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Scored only' }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sector' }), 'Industry')
    await userEvent.type(screen.getByRole('textbox', { name: 'Search ticker or name' }), 'high')
    expect(rows()).toHaveLength(1)
    expect(screen.getByText('Showing 1 of 3 stocks')).toBeVisible()
    expect(within(rows()[0]).getByRole('link')).toHaveTextContent('HIGH')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sector' }), 'Finance')
    expect(screen.getByText(/No company matches these filters/)).toBeVisible()
    expect(screen.getByText('Showing 0 of 3 stocks')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(rows()).toHaveLength(3)
    expect(screen.getByRole('checkbox', { name: 'Watchlist only' })).not.toBeChecked()
  })

  it('does not carry a sector selection into a different market', async () => {
    const { rerender } = renderWithProviders(<LongTermPage />)
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Sector' }), 'Industry')
    mocks.market.mockReturnValue({ market: 'us', markets: [], needsPicker: false, pick: mocks.pick })
    mocks.ranking.mockReturnValue(result({ market: 'us', asOf: '2026-10-21', modelVersion: 'qvm-v1', dbEnabled: true,
      items: [{ ...item('us-stock', 75), sector: 'Technology', market: 'us' }], totalCount: 1, scoredCount: 1 }))
    rerender(<LongTermPage />)
    expect(screen.getByRole('combobox', { name: 'Sector' })).toHaveValue('')
    expect(rows()).toHaveLength(1)
    expect(screen.queryByRole('option', { name: 'Industry' })).not.toBeInTheDocument()
  })

  it('retains stale rows, distinguishes source dates from load time and retries without hiding them', async () => {
    const retry = vi.fn()
    const failed = { ...result({ market: 'gpw', asOf: '2026-10-21', modelVersion: 'qvm-v1', dbEnabled: true, items, totalCount: 3, scoredCount: 2 }), error: true, stale: true, refetch: retry }
    mocks.ranking.mockReturnValue(failed)
    const { rerender } = renderWithProviders(<LongTermPage />)
    const status = screen.getByRole('region', { name: 'Data status' })
    expect(within(status).getByText('2026-10-21')).toBeVisible()
    expect(within(status).getByText(new Date(failed.lastUpdated).toLocaleString('en', { dateStyle: 'short', timeStyle: 'short' }))).toBeVisible()
    expect(within(status).getByText(/Financial observations · oldest to newest/)).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('Showing the last successfully loaded results')
    expect(rows()).toHaveLength(3)
    await userEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalledOnce()
    mocks.ranking.mockReturnValue({ ...failed, loading: true, error: false })
    rerender(<LongTermPage />)
    expect(screen.getByRole('alert')).toBeVisible()
    expect(rows()).toHaveLength(3)
    expect(within(screen.getByRole('alert')).getByRole('button', { name: 'Reloading…' })).toBeDisabled()
  })

  it('offers retry on errors and shows Polish labels and missing reasons', async () => {
    await i18n.changeLanguage('pl')
    const retry = vi.fn()
    mocks.ranking.mockReturnValue({ ...result({ market: 'gpw', asOf: null, modelVersion: 'qvm-v1', dbEnabled: true, items, totalCount: 3, scoredCount: 2 }), error: true, refetch: retry })
    renderWithProviders(<LongTermPage />)
    expect(screen.getByRole('heading', { name: 'Ranking długoterminowy: jakość + wycena + momentum' })).toBeInTheDocument()
    expect(screen.getByText('Brak danych finansowych')).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('alert')).getByRole('button'))
    expect(retry).toHaveBeenCalledOnce()
  })
})
