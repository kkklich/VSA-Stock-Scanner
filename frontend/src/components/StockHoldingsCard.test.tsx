import { beforeEach, expect, it, vi } from 'vitest'
import { type StockHoldings, portfolioRequest } from '../api/portfoliosApi'
import type { ApiStockSignals } from '../api/stocksApi'
import { AuthContext, type AuthContextValue } from '../hooks/useAuth'
import i18n from '../i18n'
import { fireEvent, renderWithProviders, screen, within } from '../test/utils'
import { StockHoldingsCard } from './StockHoldingsCard'

vi.mock('../api/portfoliosApi', () => ({ portfolioRequest: vi.fn() }))

const holdingsRequest = vi.mocked(portfolioRequest)
const holdings: StockHoldings = {
  quantity: 8.75,
  wallets: [
    { id: 'first', name: 'Retirement', quantity: 6.5 },
    { id: 'second', name: 'Investing', quantity: 2.25 },
  ],
}

function card(owner: number, ticker = 'aapl.us', quote?: Pick<ApiStockSignals, 'lastPrice' | 'currency'>) {
  const auth: AuthContextValue = {
    user: {
      id: owner, email: 'owner@example.com', displayName: 'Owner', role: 'user', emailVerified: true,
      createdAt: '2026-01-01T00:00:00Z', lastLoginAt: null,
    },
    loading: false,
    config: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    changePassword: vi.fn(),
  }
  return <AuthContext.Provider value={auth}><StockHoldingsCard ticker={ticker} quote={quote} /></AuthContext.Provider>
}

beforeEach(async () => {
  holdingsRequest.mockReset()
  await i18n.changeLanguage('en')
})

it.each([
  { ticker: 'aapl.us', currency: 'USD', lastPrice: 24, valueCurrency: 'USD' },
  { ticker: 'hsba.l', currency: 'GBp', lastPrice: 2400, valueCurrency: 'GBP' },
])('values fractional shares for $ticker across all wallets', async ({ ticker, currency, lastPrice, valueCurrency }) => {
  holdingsRequest.mockResolvedValue(holdings)
  renderWithProviders(card(12, ticker, { lastPrice, currency }))

  expect(await screen.findByText('8.75')).toBeInTheDocument()
  expect(screen.getByText('Total shares')).toBeInTheDocument()
  expect(screen.getByText('Current value')).toBeInTheDocument()
  expect(screen.getByText(`210.00 ${valueCurrency}`)).toBeInTheDocument()
  const [first, second] = screen.getAllByRole('listitem')
  expect(first).toHaveTextContent('Retirement')
  expect(within(first).getByText('6.5')).toBeInTheDocument()
  expect(within(first).getByText(`156.00 ${valueCurrency}`)).toBeInTheDocument()
  expect(second).toHaveTextContent('Investing')
  expect(within(second).getByText('2.25')).toBeInTheDocument()
  expect(within(second).getByText(`54.00 ${valueCurrency}`)).toBeInTheDocument()
  expect(holdingsRequest).toHaveBeenCalledWith('GET', `/holdings/${ticker}`, undefined, expect.any(AbortSignal), 12)
})

it('shows share counts without a quote and updates value when a price arrives', async () => {
  holdingsRequest.mockResolvedValue(holdings)
  const { rerender } = renderWithProviders(card(12, 'kgh', { lastPrice: 0, currency: 'PLN' }))
  expect(await screen.findByText('8.75')).toBeInTheDocument()
  expect(screen.getByText('Price unavailable')).toBeInTheDocument()

  rerender(card(12, 'kgh', { lastPrice: 24, currency: 'PLN' }))
  expect(screen.getByText('210.00 PLN')).toBeInTheDocument()
  expect(holdingsRequest).toHaveBeenCalledTimes(1)
})

it('collapses to the title and reopens the loaded holdings', async () => {
  holdingsRequest.mockResolvedValue(holdings)
  renderWithProviders(card(12, 'aapl.us', { lastPrice: 24, currency: 'USD' }))
  const toggle = screen.getByRole('button', { name: 'My holdings' })
  const total = await screen.findByText('210.00 USD')
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(total).toBeVisible()

  fireEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  expect(toggle).toBeVisible()
  expect(total).not.toBeVisible()
  expect(screen.queryByRole('link', { name: 'My portfolio' })).not.toBeInTheDocument()

  fireEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(total).toBeVisible()
  expect(screen.getByRole('link', { name: 'My portfolio' })).toBeVisible()
  expect(holdingsRequest).toHaveBeenCalledTimes(1)
})

it('clears the holdings when navigating to a different stock or signing out', async () => {
  holdingsRequest.mockResolvedValueOnce(holdings).mockResolvedValueOnce({ quantity: 0, wallets: [] })
  const { rerender } = renderWithProviders(card(12))
  expect(await screen.findByText('Retirement')).toBeInTheDocument()

  rerender(card(12, 'kgh'))
  expect(screen.queryByText('Retirement')).not.toBeInTheDocument()
  expect(await screen.findByText('You have no open position in this stock.')).toBeInTheDocument()

  rerender(<StockHoldingsCard ticker="kgh" />)
  expect(screen.queryByRole('region', { name: 'My holdings' })).not.toBeInTheDocument()
  expect(holdingsRequest).toHaveBeenCalledTimes(2)
})

it('allows retry after a failed holdings request', async () => {
  holdingsRequest.mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce(holdings)
  renderWithProviders(card(12))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load holdings.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('Retirement')).toBeInTheDocument()
})
