import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { journalRequest, type JournalEntry, type NewJournalEntry } from '../api/journalApi'
import { fetchRanking, type ApiStockSignals } from '../api/stocksApi'
import { useStockDetail } from '../hooks/useStockDetail'
import { JournalPanel } from './JournalPanel'

const auth = vi.hoisted(() => ({ user: { id: 1 } as { id: number } | null, loading: false, config: { enabled: true } }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../hooks/useStockDetail', () => ({ useStockDetail: vi.fn() }))
vi.mock('../api/journalApi', () => ({ journalRequest: vi.fn() }))
vi.mock('../api/stocksApi', () => ({ fetchRanking: vi.fn() }))
vi.mock('./StockChart', () => ({ StockChart: ({ candles }: { candles: unknown }) => <div data-testid="chart">{JSON.stringify(candles)}</div> }))

const data: ApiStockSignals = {
  ticker: 'PKN', name: 'Orlen', sector: null, currency: 'PLN', market: 'gpw',
  lastPrice: 100, currentRating: 70, priceChangePct: 1, ratingChange: 2,
  history: [{ time: '2026-10-28', open: 98, high: 101, low: 97, close: 100, volume: 1000 }],
  vsaSignals: [], methodSignals: [], interval: '1d', intraday: false, historyStart: '2026-10-28',
  weeklyRating: null, weeklySignal: null, weeklyAgreement: null,
}

function App() {
  return <MemoryRouter><JournalPanel ticker="PKN" data={data} /></MemoryRouter>
}

let saved: JournalEntry | null
beforeEach(() => {
  vi.resetAllMocks()
  auth.user = { id: 1 }
  saved = null
  vi.mocked(fetchRanking).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(useStockDetail).mockReturnValue({
    data: { ...data, history: [{ time: '2026-10-29', open: 100, high: 112, low: 99, close: 110, volume: 2000 }] },
    loading: false, error: null, noDataForInterval: false,
  })
  vi.mocked(journalRequest).mockImplementation(async (method, path, body) => {
    if (method === 'POST') {
      saved = { ...structuredClone(body as NewJournalEntry), status: 'observing', review: '', version: 1, createdAt: '2026-10-29T12:00:00Z', updatedAt: '2026-10-29T12:00:00Z' }
      return saved
    }
    if (method === 'PATCH') {
      saved = { ...saved!, ...(body as { status: JournalEntry['status']; review: string }), version: 2 }
      return saved
    }
    if (method === 'DELETE') { saved = null; return { ok: true } }
    if (path?.startsWith('?')) return { items: saved ? [saved] : [], total: saved ? 1 : 0 }
    return saved
  })
})

describe('private observation journal', () => {
  it('requires an account and does not fetch or store guest notes', () => {
    auth.user = null
    render(<App />)
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeVisible()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(journalRequest).not.toHaveBeenCalled()
  })

  it('saves the scenario and frozen chart, then compares and updates only its outcome', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/No observations yet/)
    await user.type(screen.getByLabelText('Observation / scenario'), 'Watching a breakout')
    await user.type(screen.getByLabelText('Confirmation conditions'), 'Close above 105')
    await user.type(screen.getByLabelText('Invalidation conditions'), 'Close below 95')
    await user.click(screen.getByRole('button', { name: 'Save observation' }))
    await screen.findByText('Observation saved to your account.')
    const frozen = structuredClone(saved!.snapshot)
    expect(saved!.confirmation).toBe('Close above 105')
    expect(frozen.referencePrice).toBe(100)
    expect(frozen.history).toEqual(data.history)
    await user.click(screen.getByRole('button', { name: 'Open saved chart and outcome' }))
    await screen.findByLabelText('Follow-up / conclusions')
    await user.click(screen.getByRole('button', { name: 'Compare with current chart' }))
    expect(screen.getAllByTestId('chart')).toHaveLength(2)
    expect(screen.getAllByTestId('chart')[0]).toHaveTextContent('2026-10-28')
    expect(screen.getAllByTestId('chart')[1]).toHaveTextContent('2026-10-29')
    await user.selectOptions(screen.getByLabelText('Scenario status'), 'confirmed')
    await user.type(screen.getByLabelText('Follow-up / conclusions'), 'Confirmed on higher volume')
    await user.click(screen.getByRole('button', { name: 'Save outcome' }))
    await waitFor(() => expect(saved!.status).toBe('confirmed'))
    expect(saved!.snapshot).toEqual(frozen)
    const patch = vi.mocked(journalRequest).mock.calls.find(([method]) => method === 'PATCH')![2]
    expect(patch).toEqual({ version: 1, status: 'confirmed', review: 'Confirmed on higher volume' })
    await user.click(screen.getByRole('button', { name: 'Delete entry' }))
    expect(saved).not.toBeNull()
    await user.click(screen.getByRole('button', { name: 'Confirm deletion' }))
    await waitFor(() => expect(saved).toBeNull())
  })

  it('keeps the form and reuses the same snapshot ID after an uncertain save', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/No observations yet/)
    await user.type(screen.getByLabelText('Observation / scenario'), 'Test retry')
    vi.mocked(journalRequest).mockRejectedValueOnce(new ApiError(0, 'Offline'))
    await user.click(screen.getByRole('button', { name: 'Save observation' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Observation / scenario')).toHaveValue('Test retry')
    expect(screen.queryByText('Observation saved to your account.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save observation' }))
    await screen.findByText('Observation saved to your account.')
    const posts = vi.mocked(journalRequest).mock.calls.filter(([method]) => method === 'POST')
    expect(posts[0][2]).toEqual(posts[1][2])
    expect(fetchRanking).toHaveBeenCalledTimes(1)
  })

  it('clears account notes and aborts a pending request on account switch', async () => {
    let resolve!: (value: unknown) => void
    vi.mocked(journalRequest).mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const view = render(<App />)
    fireEvent.change(screen.getByLabelText('Observation / scenario'), { target: { value: 'Private A' } })
    const signal = vi.mocked(journalRequest).mock.calls[0][3]
    auth.user = { id: 2 }
    view.rerender(<App />)
    expect(signal?.aborted).toBe(true)
    expect(screen.getByLabelText('Observation / scenario')).toHaveValue('')
    await act(async () => resolve({ items: [], total: 0 }))
    expect(screen.queryByText('Private A')).not.toBeInTheDocument()
    auth.user = null
    view.rerender(<App />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
