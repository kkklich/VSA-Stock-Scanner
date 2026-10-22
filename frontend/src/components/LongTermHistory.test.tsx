import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, within } from '../test/utils'
import type { LongTermItem } from '../types/longTerm'
import { LongTermHistory } from './LongTermHistory'

const mocks = vi.hoisted(() => ({ scores: vi.fn(), financials: vi.fn() }))
vi.mock('../hooks/useLongTerm', () => ({ useLongTermHistory: mocks.scores, useFinancialHistory: mocks.financials }))

const item: LongTermItem = {
  ticker: 'kgh', name: 'KGHM', sector: null, market: 'gpw', currency: 'PLN', asOf: '2026-10-21',
  score: 70, qualityScore: 80, valueScore: 60, momentumScore: 70, coverage: 100, eligible: true,
  missing: [], inputs: { roe: 0.12, earningsYield: 0, momentum12_1: 0.3 },
  fundamentalsObservedAt: '2026-10-22T10:00:00Z', comparisonGroup: 'market', peerCount: 10,
}
const scoreData = { ticker: 'kgh', dbEnabled: true, items: [
  { ...item, score: 70, recordedAt: '2026-10-22T10:00:02Z', modelVersion: 'qvm-v1' },
  { ...item, score: null, recordedAt: '2026-10-22T10:00:01Z', modelVersion: 'qvm-v1' },
  { ...item, score: 60, recordedAt: '2026-10-22T10:00:00Z', modelVersion: 'qvm-v1' },
] }
const financialData = { ticker: 'kgh', dbEnabled: true, items: [
  { observedAt: '2026-10-22T10:00:00Z', kind: 'quarterly', source: 'yahoo', payload: { financialCurrency: 'EUR', reports: [{ periodEnd: '2026-06-30', totalRevenue: 1000 }] } },
] }
function result<T>(data: T | null) { return { data, loading: false, error: false, refetch: vi.fn() } }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.scores.mockImplementation((ticker) => result(ticker ? scoreData : null))
  mocks.financials.mockImplementation((ticker) => result(ticker ? financialData : null))
})

describe('LongTermHistory tabs', () => {
  it('starts with current inputs and fetches only the selected history', async () => {
    renderWithProviders(<LongTermHistory item={item} close={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('12%')).toBeVisible()
    expect(screen.getByText(/not an observed 0% earnings yield/)).toBeVisible()
    expect(mocks.scores).toHaveBeenLastCalledWith(null)
    expect(mocks.financials).toHaveBeenLastCalledWith(null)
    await userEvent.click(screen.getByRole('tab', { name: 'Score history' }))
    expect(mocks.scores).toHaveBeenLastCalledWith('kgh')
    expect(mocks.financials).toHaveBeenLastCalledWith(null)
    const scores = screen.getByRole('region', { name: 'Recorded scores' })
    expect(scores.querySelectorAll('summary')).toHaveLength(3)
    expect(screen.getByRole('img')).toBeVisible()
    expect(scores.querySelectorAll('circle')).toHaveLength(2)
    expect(scores.querySelectorAll('polyline')).toHaveLength(0)
    await userEvent.click(scores.querySelectorAll('summary')[1])
    expect(scores.querySelector('time[datetime="2026-10-22T10:00:01Z"]')).toHaveAttribute('title', '2026-10-22T10:00:01Z')
    await userEvent.click(screen.getByRole('tab', { name: 'Financial data' }))
    expect(mocks.scores).toHaveBeenLastCalledWith(null)
    expect(mocks.financials).toHaveBeenLastCalledWith('kgh')
    expect(screen.queryByRole('region', { name: 'Recorded scores' })).not.toBeInTheDocument()
    const financials = screen.getByRole('region', { name: 'Financial observations' })
    await userEvent.click(financials.querySelector('summary')!)
    expect(within(financials).getByText('2026-06-30')).toBeVisible()
    expect(within(financials).getByText(/Reporting currency at observation: EUR/)).toBeVisible()
    expect(within(financials).getByText(/1,000 \(currency not recorded\)/)).toBeVisible()
  })

  it('supports roving keyboard navigation, wrapping, Home and End', async () => {
    renderWithProviders(<LongTermHistory item={item} close={vi.fn()} />)
    const overview = screen.getByRole('tab', { name: 'Overview' })
    const scores = screen.getByRole('tab', { name: 'Score history' })
    const financials = screen.getByRole('tab', { name: 'Financial data' })
    overview.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(scores).toHaveFocus()
    expect(scores).toHaveAttribute('aria-selected', 'true')
    expect(overview).toHaveAttribute('tabindex', '-1')
    await userEvent.keyboard('{End}')
    expect(financials).toHaveFocus()
    await userEvent.keyboard('{ArrowRight}')
    expect(overview).toHaveFocus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(financials).toHaveFocus()
    await userEvent.keyboard('{Home}')
    expect(overview).toHaveFocus()
    const panel = screen.getByRole('tabpanel', { name: 'Overview' })
    expect(overview).toHaveAttribute('aria-controls', panel.id)
    for (const tab of screen.getAllByRole('tab')) expect(document.getElementById(tab.getAttribute('aria-controls')!)).not.toBeNull()
  })

  it('renders archived dividend yield in percentage points and ROE as a fraction', async () => {
    mocks.financials.mockImplementation((ticker) => result(ticker ? { ticker: 'kgh', dbEnabled: true, items: [
      { observedAt: '2026-10-22T10:00:00Z', kind: 'fundamentals', source: 'yahoo', payload: { dividendYield: 0.51, returnOnEquity: 0.184, financialCurrency: 'EUR' } },
    ] } : null))
    renderWithProviders(<LongTermHistory item={item} close={vi.fn()} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Financial data' }))
    const financials = screen.getByRole('region', { name: 'Financial observations' })
    await userEvent.click(financials.querySelector('summary')!)
    expect(within(financials).getByText('0.51%')).toBeVisible()
    expect(within(financials).getByText('18.4%')).toBeVisible()
    expect(within(financials).queryByText('51%')).not.toBeInTheDocument()
  })

  it('resets to Overview when the selected stock changes without fetching its history prematurely', async () => {
    const { rerender } = renderWithProviders(<LongTermHistory item={item} close={vi.fn()} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Score history' }))
    mocks.scores.mockClear()
    rerender(<LongTermHistory item={{ ...item, ticker: 'pko', name: 'PKO' }} close={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(mocks.scores).toHaveBeenLastCalledWith(null)
    expect(mocks.scores).not.toHaveBeenCalledWith('pko')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    rerender(<LongTermHistory item={item} close={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps storage failure and request retry distinct from insufficient chart history', async () => {
    const retry = vi.fn()
    mocks.scores.mockReturnValue({ data: null, loading: false, error: true, refetch: retry })
    mocks.financials.mockReturnValue(result({ ticker: 'kgh', dbEnabled: false, items: [] }))
    renderWithProviders(<LongTermHistory item={item} close={vi.fn()} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Score history' }))
    expect(screen.getByRole('alert')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/two or more distinct times/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Financial data' }))
    expect(screen.getByText(/History storage is unavailable/i)).toBeVisible()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
