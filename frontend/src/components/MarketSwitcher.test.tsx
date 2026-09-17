// The top bar's market switcher: invisible on a GPW-only site, a select of
// the served markets (plus "All markets") otherwise, remembered per browser.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, waitFor } from '../test/utils'
import type { ApiMarket } from '../api/stocksApi'
import { GPW_ONLY, resetMarketsCache } from '../hooks/useMarkets'
import { MARKET_STORAGE_KEY } from '../lib/markets'

const { fetchMarketsMock } = vi.hoisted(() => ({ fetchMarketsMock: vi.fn() }))

vi.mock('../api/stocksApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/stocksApi')>()),
  fetchMarkets: fetchMarketsMock,
}))

import { MarketSwitcher } from './MarketSwitcher'

const US: ApiMarket = {
  ...GPW_ONLY[0],
  id: 'us',
  name: 'US stock market (NASDAQ and NYSE)',
  shortName: 'USA',
  country: 'United States',
  region: 'usa',
  currency: 'USD',
  majorCurrency: 'USD',
  timezone: 'America/New_York',
  tickerSuffix: '.us',
  refreshRun: 'us',
  companyCount: 518,
}

beforeEach(() => {
  localStorage.clear()
  resetMarketsCache()
  fetchMarketsMock.mockReset()
})

describe('MarketSwitcher', () => {
  it('stays hidden when only the GPW is served', async () => {
    fetchMarketsMock.mockResolvedValue(GPW_ONLY)
    const { container } = renderWithProviders(<MarketSwitcher />)
    await waitFor(() => expect(fetchMarketsMock).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('stays hidden when the backend has no catalogue', async () => {
    fetchMarketsMock.mockRejectedValue(new Error('404'))
    const { container } = renderWithProviders(<MarketSwitcher />)
    await waitFor(() => expect(fetchMarketsMock).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('asks again after a failed catalogue request', async () => {
    // The backend was restarting: the first mount gets nothing…
    fetchMarketsMock.mockRejectedValueOnce(new Error('502'))
    const first = renderWithProviders(<MarketSwitcher />)
    await waitFor(() => expect(fetchMarketsMock).toHaveBeenCalledTimes(1))
    first.unmount()

    // …and the next one (another page) gets the real catalogue.
    fetchMarketsMock.mockResolvedValue([GPW_ONLY[0], US])
    renderWithProviders(<MarketSwitcher />)
    expect(await screen.findByRole('combobox', { name: 'Market' })).toBeInTheDocument()
    expect(fetchMarketsMock).toHaveBeenCalledTimes(2)
  })

  it('offers every served market and all of them, and remembers the choice', async () => {
    fetchMarketsMock.mockResolvedValue([GPW_ONLY[0], US])
    renderWithProviders(<MarketSwitcher />)
    const select = await screen.findByRole('combobox', { name: 'Market' })
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['GPW (Poland)', 'USA', 'All markets'])
    expect(select).toHaveValue('gpw')

    await userEvent.selectOptions(select, 'us')
    expect(localStorage.getItem(MARKET_STORAGE_KEY)).toBe('us')
    expect(select).toHaveValue('us')
  })

  it('shows a stored market the site no longer serves as the GPW', async () => {
    localStorage.setItem(MARKET_STORAGE_KEY, 'de')
    fetchMarketsMock.mockResolvedValue([GPW_ONLY[0], US])
    renderWithProviders(<MarketSwitcher />)
    expect(await screen.findByRole('combobox', { name: 'Market' })).toHaveValue('gpw')
  })
})
