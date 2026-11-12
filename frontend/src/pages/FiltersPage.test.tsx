import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, waitFor } from '../test/utils'
import { EMPTY_FILTERS, FILTER_PRESETS_KEY, loadPresets, type FilterPreset } from '../lib/filterPresets'
import { AuthContext, type AuthContextValue } from '../hooks/useAuth'
import * as presetApi from '../api/filterPresetsApi'
import { FiltersPage } from './FiltersPage'

const { useRankingMock } = vi.hoisted(() => ({ useRankingMock: vi.fn() }))
vi.mock('../hooks/useRanking', () => ({ useRanking: useRankingMock }))
vi.mock('../hooks/useCompanies', () => ({ useCompanies: () => ({ companies: [] }) }))
vi.mock('../hooks/useMarkets', () => ({
  useMarketScope: () => ({ market: 'gpw', markets: [{ id: 'gpw', currency: 'PLN' }] }),
}))
vi.mock('../hooks/useRankingColumns', () => ({
  useRankingColumns: () => ({ renderColumns: [], stored: {}, order: [], count: 0 }),
  sortOptionsFrom: () => [],
}))
vi.mock('../components/ColumnPicker', () => ({ ColumnPicker: () => null }))
vi.mock('../api/filterPresetsApi')

beforeEach(() => {
  localStorage.clear()
  useRankingMock.mockReturnValue({
    data: [], total: 0, loading: false, error: null, refetch: vi.fn(),
  })
})

describe('account presets', () => {
  const session: AuthContextValue = {
    user: { id: 42, email: 'test@example.com', displayName: 'Test', role: 'user',
      emailVerified: false, createdAt: '2026-01-01', lastLoginAt: null },
    config: null, loading: false, signIn: vi.fn(), signUp: vi.fn(),
    signOut: vi.fn(), changePassword: vi.fn(),
  }
  const page = <AuthContext.Provider value={session}><FiltersPage /></AuthContext.Provider>

  it('saves once after a lost reply, then applies and deletes the preset in a fresh session', async () => {
    const user = userEvent.setup()
    let stored: FilterPreset[] = []
    vi.mocked(presetApi.getFilterPresets).mockImplementation(async () => [...stored])
    const add = vi.mocked(presetApi.addFilterPresets)
    add.mockImplementationOnce(async ([preset]) => {
      stored = [preset]
      throw new Error('Lost reply')
    }).mockImplementationOnce(async ([preset]) => {
      expect(preset).toEqual(stored[0])
      return [...stored]
    })
    vi.mocked(presetApi.deleteFilterPreset).mockImplementation(async (id) => {
      stored = stored.filter(preset => preset.id !== id)
      return [...stored]
    })

    const firstDevice = renderWithProviders(page, { initialEntries: ['/filters?q=KGH&minPrice=20'] })
    const openForm = screen.getByRole('button', { name: 'Save preset' })
    await waitFor(() => expect(openForm).toBeEnabled())
    await user.click(openForm)
    await user.type(screen.getByPlaceholderText('Preset name…'), 'My metals')
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t sync presets')
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await screen.findByRole('button', { name: 'My metals', exact: true })
    expect(loadPresets()).toEqual([])
    firstDevice.unmount()

    renderWithProviders(page)
    await user.click(await screen.findByRole('button', { name: 'My metals', exact: true }))
    await waitFor(() => expect(useRankingMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'KGH', minPrice: 20 }), expect.anything(),
    ))
    await user.click(screen.getByRole('button', { name: /Delete preset.*My metals/ }))
    expect(screen.queryByRole('button', { name: 'My metals', exact: true })).toBeNull()
    expect(stored).toEqual([])
  })
})

describe('insider filters', () => {
  it.each(['insiderLatestTransaction', 'insiderTotalValue', 'insiderValueLast30Days'])(
    'selects %s as the primary order and restores it from a link', async (key) => {
      const user = userEvent.setup()
      const view = renderWithProviders(<FiltersPage />)
      await user.selectOptions(screen.getByRole('combobox', { name: /^Sort insider activity/ }), key)
      expect(useRankingMock).toHaveBeenLastCalledWith(expect.objectContaining({
        sort: [{ key, dir: 'desc' }], insiderDays: 100,
      }), expect.anything())
      await user.selectOptions(screen.getByRole('combobox', { name: /^Insider sort direction/ }), 'asc')
      expect(useRankingMock).toHaveBeenLastCalledWith(expect.objectContaining({
        sort: [{ key, dir: 'asc' }],
      }), expect.anything())
      view.unmount()
      renderWithProviders(<FiltersPage />, {
        initialEntries: [`/filters?sortBy=${key}&sortDir=asc&insiderDays=365`],
      })
      expect(useRankingMock).toHaveBeenLastCalledWith(expect.objectContaining({
        sort: [{ key, dir: 'asc' }], insiderDays: 365,
      }), expect.anything())
    },
  )

  it('restores screener criteria and sorting from the URL on the first request', () => {
    renderWithProviders(<FiltersPage />, {
      initialEntries: ['/filters?q=KGH&minPrice=20&maxPrice=250&minVolume=1000&range52w=newHigh&insiderActivity=buy&insiderDays=180&insiderEnd=2025-06-01&minInsiderValue=250000&sortBy=lastPrice&sortDir=asc'],
    })
    expect(useRankingMock).toHaveBeenLastCalledWith(expect.objectContaining({
      q: 'KGH', minPrice: 20, maxPrice: 250, minVolume: 1000, new52wHigh: true,
      insiderActivity: 'buy', insiderDays: 180, insiderEnd: '2025-06-01', minInsiderValue: 250000,
      sort: [{ key: 'lastPrice', dir: 'asc' }],
    }), expect.anything())
  })

  it('sends activity, period and amount, persists a preset and clears all', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FiltersPage />)
    await user.selectOptions(screen.getByRole('combobox', { name: /^Insider activity/ }), 'netSell')
    await user.selectOptions(screen.getByRole('combobox', { name: /^Insider transaction period/ }), '180')
    await user.type(screen.getByRole('spinbutton', { name: 'Min. insider value (PLN)' }), '250000')
    await waitFor(() => expect(useRankingMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        insiderActivity: 'netSell', insiderDays: 180, minInsiderValue: 250000,
        sort: [{ key: 'insiderLatestTransaction', dir: 'desc' }],
      }),
      expect.anything(),
    ))
    await user.click(screen.getByRole('button', { name: /Save preset/ }))
    await user.type(screen.getByPlaceholderText('Preset name…'), 'Insider sales')
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }))
    expect(loadPresets()[0].filters).toMatchObject({
      insiderActivity: 'netSell', insiderDays: 180, minInsiderValue: 250000,
    })

    await user.click(screen.getByRole('button', { name: /Clear all/ }))
    await waitFor(() => expect(useRankingMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ insiderActivity: undefined, insiderDays: undefined, minInsiderValue: undefined }),
      expect.anything(),
    ))
    await user.click(screen.getByRole('button', { name: 'Insider sales', exact: true }))
    await waitFor(() => expect(useRankingMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ insiderActivity: 'netSell', insiderDays: 180, minInsiderValue: 250000 }),
      expect.anything(),
    ))
  })

  it('loads older presets with safe insider defaults', () => {
    localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify([{
      id: 'old', name: 'Mining', filters: { sector: 'Mining' },
    }]))
    expect(loadPresets()[0].filters).toEqual({ ...EMPTY_FILTERS, sector: 'Mining' })
  })

  it('shows the matching amounts and unknown values on desktop and mobile', async () => {
    localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify([{
      id: 'buy', name: 'Insider buys', filters: { ...EMPTY_FILTERS, insiderActivity: 'buy' },
    }]))
    useRankingMock.mockReturnValue({
      data: [{
        ticker: 'kgh', name: 'KGHM', insiderActivity: {
          purchasesCount: 2, salesCount: 1, purchasesShares: 5000, salesShares: 500,
          purchasesValuePln: 250000, salesValuePln: 500, netValuePln: 249500,
          latestTransactionDate: '2026-11-04', totalValuePln: 250000, valueLast30DaysPln: null,
        },
      }],
      total: 1, loading: false, error: null, refetch: vi.fn(),
    })
    const user = userEvent.setup()
    renderWithProviders(<FiltersPage />)
    await user.click(screen.getByRole('button', { name: 'Insider buys', exact: true }))
    await waitFor(() => expect(screen.getAllByText(/250,000\.00 PLN/)).toHaveLength(4))
    expect(screen.getAllByText('2026-11-04')).toHaveLength(2)
    expect(screen.getAllByText(/-500\.00 PLN/)).toHaveLength(2)
    expect(screen.getAllByText(/2 trades · 5,000 shares/)).toHaveLength(2)
    expect(screen.getAllByText(/Unknown value/).length).toBeGreaterThanOrEqual(2)
  })
})
