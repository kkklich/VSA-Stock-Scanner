import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { importXtbWallets, portfolioRequest, previewXtbWallets, type Portfolio, type XtbWalletsPreview } from '../api/portfoliosApi'
import { PortfolioPage } from './PortfolioPage'

const auth = vi.hoisted(() => ({ user: { id: 1 } as { id: number } | null, loading: false }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../api/portfoliosApi', () => ({ portfolioRequest: vi.fn(), previewXtbWallets: vi.fn(), importXtbWallets: vi.fn() }))
const instruments = [{ ticker: 'kgh', name: 'KGHM', currency: 'PLN', market: 'gpw' }]
const makePortfolio = (): Portfolio => ({
  id: 'portfolio-1', name: 'Retirement', broker: 'XTB', version: 1,
  costMethod: 'fifo', brokerAccountId: null,
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
  it('keeps the all-wallet value visible when switching the selected portfolio', async () => {
    portfolios.push({ ...makePortfolio(), id: 'second-wallet', name: 'Savings' })
    const original = vi.mocked(portfolioRequest).getMockImplementation()!
    const current = { date: '2026-01-06', value: 2500, missingQuotes: 0, missingRates: [], staleQuotes: 0 }
    vi.mocked(portfolioRequest).mockImplementation(async (method, path, ...args) => {
      const data = await original(method, path, ...args)
      return path === '' || path === '?historyRange=all' ? { ...(data as object), summary: {
        currency: 'PLN', current, history: [current], dayChange: null, weekChange: null, currencyTotals: [], missingHoldings: [],
      } } : data
    })

    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'All wallets' })).toBeVisible()
    expect(screen.getAllByRole('heading', { name: 'Import from XTB' })).toHaveLength(1)
    expect(screen.getByText('2,500.00 PLN', { selector: 'dd' })).toBeVisible()
    expect(screen.getByText(/overlapping XTB imports/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'All time' }))
    expect(vi.mocked(portfolioRequest)).toHaveBeenCalledWith('GET', '?historyRange=all', undefined, expect.any(AbortSignal), 1)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled())
    expect(screen.getByRole('button', { name: 'All time' })).toHaveAttribute('aria-pressed', 'true')
    vi.mocked(portfolioRequest).mockRejectedValueOnce(new ApiError(0, 'Offline'))
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByText(/Showing the valuation from/)).toBeVisible()
    await user.selectOptions(screen.getByLabelText('Choose portfolio'), 'second-wallet')
    expect(screen.getByRole('heading', { name: 'Savings' })).toBeVisible()
    expect(screen.getByText('2,500.00 PLN', { selector: 'dd' })).toBeVisible()
    expect(screen.getByText(/Showing the valuation from/)).toBeVisible()
  })

  it('ranks wallet heatmap values in PLN and switches comparison and wallet selection', async () => {
    portfolios.push(
      { ...makePortfolio(), id: 'largest-wallet', name: 'Savings', brokerAccountCurrency: 'EUR' },
      { ...makePortfolio(), id: 'unpriced-wallet', name: 'Unpriced' },
      { ...makePortfolio(), id: 'empty-wallet', name: 'Empty' },
    )
    const point = { date: '2026-01-06', value: 2500, missingQuotes: 0, missingRates: [], staleQuotes: 0 }
    const change = { amount: -120, percent: -10, since: '2025-12-30', partial: true }
    const original = vi.mocked(portfolioRequest).getMockImplementation()!
    vi.mocked(portfolioRequest).mockImplementation(async (method, path, ...args) => {
      const data = await original(method, path, ...args)
      return path === '' ? { ...(data as object), summary: {
        currency: 'PLN', current: point, history: [point], dayChange: null, weekChange: null,
        currencyTotals: [], missingHoldings: [], wallets: [
          { walletId: 'portfolio-1', current: { ...point, value: 500 }, dayChange: null, weekChange: change },
          { walletId: 'largest-wallet', current: { ...point, value: 2000 }, dayChange: {
            amount: 100, percent: 5, since: '2026-01-05', partial: false,
          }, weekChange: change },
          { walletId: 'unpriced-wallet', current: { ...point, value: null, missingQuotes: 1 }, dayChange: null, weekChange: null },
          { walletId: 'empty-wallet', current: { ...point, value: 0 }, dayChange: null, weekChange: null },
        ],
      } } : data
    })
    const user = userEvent.setup()
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(600)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(240)
    render(<App />)
    const heatmap = within(await screen.findByRole('region', { name: 'Wallet heatmap' }))
    const savingsTile = heatmap.getByRole('button', { name: 'Savings · EUR · 2,000.00 PLN · -10.00%' })
    const retirementTile = heatmap.getByRole('button', { name: 'Retirement · 500.00 PLN · -10.00%' })
    const area = (tile: HTMLElement) => parseFloat(tile.style.width) * parseFloat(tile.style.height)
    expect(area(savingsTile) / area(retirementTile)).toBeCloseTo(4)
    const ranking = heatmap.getAllByRole('list').at(-1)!
    const rows = within(ranking).getAllByRole('button')
    expect(rows.map(row => row.textContent)).toEqual([
      expect.stringContaining('Savings'), expect.stringContaining('Retirement'),
      expect.stringContaining('Empty'), expect.stringContaining('Unpriced'),
    ])
    expect(rows[0]).toHaveTextContent('2,000.00 PLN')
    expect(rows[0]).toHaveTextContent('-10.00%')
    expect(rows[0]).toHaveTextContent('Partial change')
    expect(rows[2]).toHaveTextContent('0.00 PLN')
    expect(rows[3]).toHaveTextContent('Unavailable')
    await user.click(heatmap.getByRole('button', { name: '1 day' }))
    expect(rows[0]).toHaveTextContent('+5.00%')
    expect(rows[0]).toHaveTextContent('+100.00 PLN')
    await user.click(savingsTile)
    expect(rows[0]).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Choose portfolio')).toHaveValue('largest-wallet')
    expect(screen.getByRole('heading', { name: 'Savings' })).toBeVisible()
    expect(portfolioRequest).toHaveBeenCalledTimes(2)
  })

  it('imports a reconciled worksheet without displaying the adjustment table', async () => {
    portfolios = []
    const user = userEvent.setup()
    const reconciliation = { asOf: '2026-01-06', changes: [{
      ticker: 'kgh', currency: 'PLN', previousQuantity: '7', quantity: '8', previousCost: '700', cost: '800',
    }] }
    vi.mocked(previewXtbWallets).mockResolvedValue({ ready: 1, errors: 0, newWallets: 1, previewToken: 'reviewed-plan', blockingError: null, wallets: [{
      id: 'imported-wallet', name: 'Cash Operations', sheet: 'Cash Operations', version: null,
      brokerAccountId: '00123456', sourceBrokerAccountId: '00123456', linksBrokerAccount: true,
      ready: 1, duplicates: 0, errors: 0, ignored: 0, warnings: [], ledgerError: null, error: null, rows: [], reconciliation,
    }] })
    vi.mocked(importXtbWallets).mockImplementation(async () => {
      portfolios.push({ ...makePortfolio(), id: 'imported-wallet', name: 'Cash Operations', brokerAccountId: '00123456', brokerAccountCurrency: 'PLN', reconciliation })
      return { wallets: [], imported: 1, duplicates: 0, skipped: 0, created: 1 }
    })
    render(<App />)
    await user.upload(await screen.findByLabelText('XTB report file'), new File(['report'], 'IKE.xlsx'))
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    const createWallet = await screen.findByRole('button', { name: 'Create wallet' })
    expect(screen.queryByText('XTB holdings adjustment')).not.toBeInTheDocument()
    expect(screen.getByText('XTB account 00123456')).toBeVisible()
    expect(screen.queryByText('800 PLN')).not.toBeInTheDocument()
    await user.click(createWallet)
    const walletSelector = await screen.findByLabelText('Choose portfolio')
    expect(within(walletSelector).getByRole('option', { name: 'Cash Operations · XTB · 00123456 · PLN' })).toBeInTheDocument()
    expect(screen.getByText('XTB account 00123456')).toBeVisible()
    expect(screen.getByText('Account currency PLN')).toBeVisible()
    expect(screen.getByText(/Import complete\. Wallets created: 1/)).toBeVisible()
    expect(screen.queryByText('XTB holdings adjustment')).not.toBeInTheDocument()
    expect(screen.queryByText('800 PLN')).not.toBeInTheDocument()
  })

  it('freezes wallet controls and background refresh while an upload is pending', async () => {
    let resolve!: (value: XtbWalletsPreview) => void
    vi.mocked(previewXtbWallets).mockImplementation(() => new Promise(done => { resolve = done }))
    const user = userEvent.setup()
    render(<App />)
    await user.upload(await screen.findByLabelText('XTB report file'), new File(['report'], 'IKE.xlsx'))
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    expect(screen.getByLabelText('Choose portfolio')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled()
    const requests = vi.mocked(portfolioRequest).mock.calls.length
    fireEvent(window, new Event('focus'))
    expect(portfolioRequest).toHaveBeenCalledTimes(requests)
    await act(async () => resolve({ wallets: [], ready: 0, errors: 0, newWallets: 0, previewToken: 'reviewed-plan', blockingError: null }))
    expect(screen.getByLabelText('Choose portfolio')).toBeEnabled()
  })

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
    expect(post[4]).toBe(1)
  })

  it('shows the instrument name, currency totals and price date', async () => {
    portfolios[0].totals = [{ currency: 'PLN', cost: 606, marketValue: 780, unrealizedPnl: 174, unrealizedPnlPct: 28.71, realizedPnl: 74, missingQuotes: 0 }]
    portfolios[0].positions = [{ ticker: 'kgh', currency: 'PLN', quantity: 6, cost: 606, averagePrice: 101, currentPrice: 130, marketValue: 780, unrealizedPnl: 174, unrealizedPnlPct: 28.71, realizedPnl: 74, quoteDate: '2026-01-06', quoteAsOf: null, quoteSource: 'close', quoteAgeDays: 10 }]
    render(<App />)
    expect(await screen.findByText('2026-01-06')).toBeVisible()
    expect(screen.getAllByText('780.00 PLN')).toHaveLength(2)
    expect(screen.getByRole('link', { name: 'KGH' })).toHaveAttribute('href', '/stock/kgh')
    expect(within(screen.getByRole('cell', { name: 'KGH KGHM' })).getByText('KGHM')).toBeVisible()
    expect(screen.getByText('Closing price')).toBeVisible()
    expect(screen.getByText('Quote is 10 calendar days old')).toBeVisible()
  })

  it('sorts and filters positions and shows status and unrealized profit or loss', async () => {
    const winner = {
      ticker: 'kgh', currency: 'PLN', quantity: 2, cost: 200, averagePrice: 100, currentPrice: 130,
      marketValue: 260, unrealizedPnl: 60, unrealizedPnlPct: 30, realizedPnl: 0,
      quoteDate: '2026-01-06', quoteAsOf: null, quoteSource: 'close', quoteAgeDays: 0,
    } as const
    portfolios[0].positions = [winner, {
      ...winner, ticker: 'pzu', quantity: 10, unrealizedPnl: -20, unrealizedPnlPct: -10,
    }, {
      ...winner, ticker: 'aapl.us', currency: 'USD', quantity: 0, cost: 0, averagePrice: null,
      marketValue: 0, unrealizedPnl: 0, unrealizedPnlPct: null,
    }]
    const user = userEvent.setup()
    render(<App />)
    const positions = within(await screen.findByRole('region', { name: 'Portfolio positions' }))
    const tickers = () => positions.getAllByRole('link').map(link => link.textContent)
    const table = within(positions.getByRole('table'))
    expect(positions.getByLabelText('Position status')).toHaveValue('active')
    expect(tickers()).toEqual(['KGH', 'PZU'])
    expect(table.getAllByText('Active')).toHaveLength(2)
    expect(table.queryByText('Closed')).not.toBeInTheDocument()
    await user.selectOptions(positions.getByLabelText('Position status'), '')
    expect(positions.getByRole('row', { name: /AAPL.US/ })).toHaveTextContent('Closed')
    expect(positions.getByText('60.00 PLN')).toHaveClass('text-emerald-400')
    expect(positions.getByText('+30.00%')).toHaveClass('text-emerald-400')
    expect(positions.getByText('-20.00 PLN')).toHaveClass('text-rose-400')
    expect(positions.getByText('-10.00%')).toHaveClass('text-rose-400')
    const quantity = positions.getByRole('button', { name: 'Sort by Quantity' })
    await user.click(quantity)
    expect(tickers()).toEqual(['PZU', 'KGH', 'AAPL.US'])
    await user.click(quantity)
    expect(tickers()).toEqual(['AAPL.US', 'KGH', 'PZU'])
    await user.selectOptions(positions.getByLabelText('Position status'), 'closed')
    expect(tickers()).toEqual(['AAPL.US'])
    await user.click(positions.getByRole('button', { name: 'Clear filters' }))
    await user.selectOptions(positions.getByLabelText('Currency'), 'PLN')
    await user.type(positions.getByRole('searchbox', { name: 'Search ticker' }), 'PZ')
    expect(tickers()).toEqual(['PZU'])
  })

  it('sorts mixed-currency positions by PLN value and by unrealized return', async () => {
    const position = {
      ticker: 'kgh', currency: 'PLN', quantity: 1, cost: 100, averagePrice: 100, currentPrice: 120,
      marketValue: 120, unrealizedPnl: 20, unrealizedPnlPct: 20, realizedPnl: 0,
      quoteDate: '2026-01-06', quoteAsOf: null, quoteSource: 'close', quoteAgeDays: 0,
    } as const
    portfolios[0].positions = [position, {
      ...position, ticker: 'sap.de', currency: 'EUR', cost: 15, averagePrice: 15, currentPrice: 21,
      marketValue: 21, unrealizedPnl: 6, unrealizedPnlPct: 40,
    }, {
      ...position, ticker: 'aapl.us', currency: 'USD', currentPrice: 110,
      marketValue: 110, unrealizedPnl: 10, unrealizedPnlPct: 10,
    }, {
      ...position, ticker: 'pzu', marketValue: null, currentPrice: null,
      unrealizedPnl: null, unrealizedPnlPct: null, quoteDate: null, quoteSource: null, quoteAgeDays: null,
    }]
    const user = userEvent.setup()
    render(<App />)
    const positions = within(await screen.findByRole('region', { name: 'Portfolio positions' }))
    const tickers = () => positions.getAllByRole('link').map(link => link.textContent)
    const value = positions.getByRole('button', { name: 'Sort by Current value' })
    await user.click(value)
    expect(tickers()).toEqual(['AAPL.US', 'KGH', 'SAP.DE', 'PZU'])
    await user.click(value)
    expect(tickers()).toEqual(['SAP.DE', 'KGH', 'AAPL.US', 'PZU'])
    await user.click(positions.getByRole('button', { name: 'Sort by Unrealized profit / loss' }))
    expect(tickers()).toEqual(['AAPL.US', 'SAP.DE', 'KGH', 'PZU'])
    const percent = positions.getByRole('button', { name: 'Sort by Unrealized return (%)' })
    await user.click(percent)
    expect(tickers()).toEqual(['SAP.DE', 'KGH', 'AAPL.US', 'PZU'])
    await user.click(percent)
    expect(tickers()).toEqual(['AAPL.US', 'KGH', 'SAP.DE', 'PZU'])
  })

  it('sorts and filters transaction history and restores the filters when reopened', async () => {
    const trade = { date: '2026-01-02', ticker: 'kgh', side: 'buy', currency: 'PLN', quantity: '2', price: '50', fees: '0' } as const
    portfolios[0].transactions = [
      { ...trade, id: 'first' },
      { ...trade, id: 'second', date: '2026-01-07', side: 'sell', quantity: '10' },
      { ...trade, id: 'third', date: '2026-01-12', ticker: 'aapl.us', currency: 'USD', quantity: '3' },
    ]
    const user = userEvent.setup()
    render(<App />)
    const history = within(await screen.findByRole('region', { name: 'Transaction history' }))
    const dates = () => history.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('cell')[0].textContent)
    expect(history.queryByRole('table')).not.toBeInTheDocument()
    expect(history.getByRole('button', { name: 'Show history' })).toHaveAttribute('aria-expanded', 'false')
    await user.click(history.getByRole('button', { name: 'Show history' }))
    expect(dates()).toEqual(['2026-01-12', '2026-01-07', '2026-01-02'])
    await user.click(history.getByRole('button', { name: 'Sort by Quantity' }))
    expect(dates()).toEqual(['2026-01-07', '2026-01-12', '2026-01-02'])
    await user.type(history.getByRole('searchbox', { name: 'Search ticker' }), 'KGH')
    await user.selectOptions(history.getByLabelText('Type'), 'sell')
    fireEvent.change(history.getByLabelText('From date'), { target: { value: '2026-01-07' } })
    fireEvent.change(history.getByLabelText('To date'), { target: { value: '2026-01-07' } })
    expect(dates()).toEqual(['2026-01-07'])
    await user.click(history.getByRole('button', { name: 'Hide history' }))
    expect(history.queryByRole('table')).not.toBeInTheDocument()
    const show = history.getByRole('button', { name: 'Show history' })
    expect(show).toHaveAttribute('aria-expanded', 'false')
    await user.click(show)
    expect(dates()).toEqual(['2026-01-07'])
    expect(history.getByLabelText('From date')).toHaveValue('2026-01-07')
    await user.click(history.getByRole('button', { name: 'Clear filters' }))
    expect(dates()).toEqual(['2026-01-07', '2026-01-12', '2026-01-02'])
  })

  it('lets the owner choose the cost method when editing a portfolio', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.selectOptions(screen.getByLabelText('Cost basis method'), 'moving_average')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(portfolioRequest).toHaveBeenCalledWith('PATCH', '/portfolio-1', {
      version: 1, name: 'Retirement', broker: 'XTB', costMethod: 'moving_average',
    }, expect.any(AbortSignal), 1))
  })

  it('lets the owner link an existing XTB portfolio and preserves leading zeros', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    const account = screen.getByLabelText('XTB account number')
    await user.type(account, '001a')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    await user.clear(account)
    await user.type(account, '00123456')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(portfolioRequest).toHaveBeenCalledWith('PATCH', '/portfolio-1', {
      version: 1, name: 'Retirement', broker: 'XTB', costMethod: 'fifo', brokerAccountId: '00123456',
    }, expect.any(AbortSignal), 1))
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

  it('rejects a refresh with another account’s bearer and clears the old wallet view', async () => {
    let bearerOwner = 1
    const original = vi.mocked(portfolioRequest).getMockImplementation()!
    vi.mocked(portfolioRequest).mockImplementation(async (method, path, body, signal, expectedOwner) => {
      if (expectedOwner !== undefined && expectedOwner !== bearerOwner) {
        throw new ApiError(409, 'Changed account', 'account_changed')
      }
      return original(method, path, body, signal, expectedOwner)
    })
    render(<App />)
    const walletSelector = await screen.findByLabelText('Choose portfolio')
    expect(within(walletSelector).getByRole('option', { name: 'Retirement · XTB' })).toBeVisible()

    // A different tab replaced the shared token while this page still shows account 1.
    bearerOwner = 2
    portfolios = [{ ...makePortfolio(), id: 'other-owner', name: 'Other account' }]
    fireEvent(window, new Event('focus'))
    expect(await screen.findByRole('alert')).toHaveTextContent('The signed-in account changed.')
    expect(screen.queryByRole('option', { name: /Retirement|Other account/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('XTB report file')).not.toBeInTheDocument()
    expect(portfolioRequest).toHaveBeenCalledWith('GET', '', undefined, expect.any(AbortSignal), 1)
    expect(portfolioRequest).toHaveBeenCalledWith('GET', '/instruments', undefined, expect.any(AbortSignal), 1)
  })
})
