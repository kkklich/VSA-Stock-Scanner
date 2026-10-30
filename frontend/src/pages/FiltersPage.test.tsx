import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, waitFor } from '../test/utils'
import { EMPTY_FILTERS, FILTER_PRESETS_KEY, loadPresets } from '../lib/filterPresets'
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

beforeEach(() => {
  localStorage.clear()
  useRankingMock.mockReturnValue({
    data: [], total: 0, loading: false, error: null, refetch: vi.fn(),
  })
})

describe('insider filters', () => {
  it('sends activity, period and amount, persists a preset and clears all', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FiltersPage />)
    await user.selectOptions(screen.getByRole('combobox', { name: /^Insider activity/ }), 'netSell')
    await user.selectOptions(screen.getByRole('combobox', { name: /^Insider reporting period/ }), '180')
    await user.type(screen.getByRole('spinbutton', { name: /^Min\. insider value/ }), '250000')
    await waitFor(() => expect(useRankingMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ insiderActivity: 'netSell', insiderDays: 180, minInsiderValue: 250000 }),
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
          purchasesValuePln: 250000, salesValuePln: null, netValuePln: null,
        },
      }],
      total: 1, loading: false, error: null, refetch: vi.fn(),
    })
    const user = userEvent.setup()
    renderWithProviders(<FiltersPage />)
    await user.click(screen.getByRole('button', { name: 'Insider buys', exact: true }))
    await waitFor(() => expect(screen.getAllByText(/250,000\.00 PLN/)).toHaveLength(2))
    expect(screen.getAllByText(/2 trades · 5,000 shares/)).toHaveLength(2)
    expect(screen.getAllByText(/Unknown value/).length).toBeGreaterThanOrEqual(2)
  })
})
