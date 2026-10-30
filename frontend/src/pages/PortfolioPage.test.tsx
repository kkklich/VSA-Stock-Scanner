import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { portfolioRequest, type Portfolio } from '../api/portfoliosApi'
import { PortfolioPage } from './PortfolioPage'

const auth = vi.hoisted(() => ({ user: { id: 1 } as { id: number } | null, loading: false }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../api/portfoliosApi', () => ({ portfolioRequest: vi.fn() }))
const instruments = [{ ticker: 'kgh', name: 'KGHM', currency: 'PLN', market: 'gpw' }]
const makePortfolio = (): Portfolio => ({
  id: 'portfolio-1', name: 'Retirement', broker: 'XTB', version: 1,
  costMethod: 'fifo',
  createdAt: '2026-01-01T00:00:00Z', transactions: [], positions: [], totals: [],
})
let portfolios: Portfolio[]
function App() { return <MemoryRouter><PortfolioPage /></MemoryRouter> }

beforeEach(() => {
  vi.resetAllMocks()
  auth.user = { id: 1 }
  portfolios = [makePortfolio()]
  vi.mocked(portfolioRequest).mockImplementation(async (method, path, body) => {
    if (path === '/instruments') return instruments
    if (method === 'POST' && path === '') {
      const payload = body as { id: string; name: string; broker: string }
      portfolios.push({ ...makePortfolio(), ...payload })
      return payload
    }
    if (method === 'POST') { portfolios[0].version++; return portfolios[0] }
    return { items: structuredClone(portfolios), valuedAt: '2026-01-06T18:00:00Z' }
  })
})

describe('account portfolios', () => {
  it('requires sign in and does not load private data for a guest', () => {
    auth.user = null
    render(<App />)
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
    expect(portfolioRequest).not.toHaveBeenCalled()
  })

  it('creates a portfolio with a broker and records a dated purchase in quote currency', async () => {
    const user = userEvent.setup()
    portfolios = []
    render(<App />)
    await user.type(await screen.findByLabelText('Portfolio name'), 'Retirement')
    await user.type(screen.getByLabelText('Broker'), 'XTB')
    const form = screen.getByLabelText('Broker').closest('form')!
    fireEvent.submit(form)
    await screen.findByLabelText('Instrument / ticker')
    await user.type(screen.getByLabelText('Instrument / ticker'), 'KGH')
    expect(screen.getByLabelText('Quote currency')).toHaveValue('PLN')
    fireEvent.change(screen.getByLabelText('Transaction date'), { target: { value: '2026-01-02' } })
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Price per share'), '100.25')
    await user.click(screen.getByRole('button', { name: 'Add transaction' }))
    await waitFor(() => expect(screen.getByLabelText('Quantity')).toHaveValue(null))
    const post = vi.mocked(portfolioRequest).mock.calls.find(([method, path]) => method === 'POST' && path?.endsWith('/transactions'))!
    expect(post[2]).toMatchObject({ ticker: 'kgh', currency: 'PLN', date: '2026-01-02', quantity: '10', price: '100.25', fees: '0', side: 'buy', version: 1 })
    expect(post[2]).toHaveProperty('id')
  })

  it('shows currency totals and the price date supplied by the server', async () => {
    portfolios[0].totals = [{ currency: 'PLN', cost: 606, marketValue: 780, unrealizedPnl: 174, unrealizedPnlPct: 28.71, realizedPnl: 74, missingQuotes: 0 }]
    portfolios[0].positions = [{ ticker: 'kgh', currency: 'PLN', quantity: 6, cost: 606, averagePrice: 101, currentPrice: 130, marketValue: 780, unrealizedPnl: 174, unrealizedPnlPct: 28.71, realizedPnl: 74, quoteDate: '2026-01-06', quoteAsOf: null, quoteSource: 'close', quoteAgeDays: 10 }]
    render(<App />)
    expect(await screen.findByText('2026-01-06')).toBeVisible()
    expect(screen.getAllByText('780.00 PLN')).toHaveLength(2)
    expect(screen.getByRole('link', { name: 'KGH' })).toHaveAttribute('href', '/stock/kgh')
    expect(screen.getByText('Closing price')).toBeVisible()
    expect(screen.getByText('Quote is 10 calendar days old')).toBeVisible()
  })

  it('lets the owner choose the cost method when editing a portfolio', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.selectOptions(screen.getByLabelText('Cost basis method'), 'moving_average')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(portfolioRequest).toHaveBeenCalledWith('PATCH', '/portfolio-1', {
      version: 1, name: 'Retirement', broker: 'XTB', costMethod: 'moving_average',
    }, expect.any(AbortSignal)))
  })

  it('protects an open editor from overwriting a newer version loaded in the background', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.type(screen.getByLabelText('Portfolio name'), ' draft')
    portfolios[0].version = 2
    portfolios[0].name = 'Changed on another device'
    fireEvent(window, new Event('focus'))
    await screen.findByText('The portfolio changed while you were editing. Cancel and reopen the editor to use current data.')
    expect(screen.getByLabelText('Portfolio name')).toHaveValue('Retirement draft')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(vi.mocked(portfolioRequest).mock.calls.some(([method]) => method === 'PATCH')).toBe(false)
  })

  it('retains the form and transaction ID after an uncertain network result', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(await screen.findByLabelText('Instrument / ticker'), 'kgh')
    await user.type(screen.getByLabelText('Quantity'), '2')
    await user.type(screen.getByLabelText('Price per share'), '100')
    vi.mocked(portfolioRequest).mockRejectedValueOnce(new ApiError(0, 'Offline'))
    await user.click(screen.getByRole('button', { name: 'Add transaction' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Quantity')).toHaveValue(2)
    expect(screen.queryByText('Changes saved.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add transaction' }))
    await screen.findByText('Changes saved.')
    const posts = vi.mocked(portfolioRequest).mock.calls.filter(([method]) => method === 'POST')
    expect(posts[0][2]).toEqual(posts[1][2])
  })

  it('blocks writes when reloading a saved change fails, without reporting the write as failed', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(await screen.findByLabelText('Instrument / ticker'), 'kgh')
    await user.type(screen.getByLabelText('Quantity'), '2')
    await user.type(screen.getByLabelText('Price per share'), '100')
    const original = vi.mocked(portfolioRequest).getMockImplementation()!
    vi.mocked(portfolioRequest).mockImplementation(async (method, ...args) => {
      if (method === 'GET') throw new ApiError(0, 'Offline')
      return original(method, ...args)
    })
    await user.click(screen.getByRole('button', { name: 'Add transaction' }))
    await screen.findByText('Changes saved.')
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Add transaction' })).toBeDisabled()
  })

  it('clears private holdings and ignores a late response when switching accounts', async () => {
    let resolve!: (result: unknown) => void
    let signal: AbortSignal | undefined
    vi.mocked(portfolioRequest).mockImplementationOnce((_method, _path, _body, requestSignal) => {
      signal = requestSignal
      return new Promise(done => { resolve = done })
    })
    const view = render(<App />)
    auth.user = { id: 2 }
    portfolios = []
    view.rerender(<App />)
    await screen.findByLabelText('Portfolio name')
    expect(signal?.aborted).toBe(true)
    await act(async () => resolve({ items: [makePortfolio()], valuedAt: '2026-01-01T00:00:00Z' }))
    expect(screen.queryByText('Retirement')).not.toBeInTheDocument()
  })
})
