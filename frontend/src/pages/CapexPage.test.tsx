import { beforeEach, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import { CapexPage } from './CapexPage'

const { useCapexMock } = vi.hoisted(() => ({ useCapexMock: vi.fn() }))
vi.mock('../hooks/useCapex', () => ({ useCapex: useCapexMock }))
vi.mock('../hooks/useCompanies', () => ({ useCompanies: () => ({ companies: [] }) }))
vi.mock('../hooks/useMarkets', () => ({
  useSingleMarket: () => ({ market: 'gpw', markets: [], needsPicker: false, pick: vi.fn() }),
}))

beforeEach(() => {
  useCapexMock.mockReturnValue({
    items: [], meta: null, loading: false, loadingMore: false, error: null,
    hasMore: false, refetch: vi.fn(),
  })
})

it('restores investment search, filters and sorting from a link', () => {
  renderWithProviders(<CapexPage />, {
    initialEntries: ['/capex?q=KGH&sector=Mining&currency=all&withData=0&sortBy=sector,capex&sortDir=asc,desc'],
  })
  expect(useCapexMock.mock.calls.at(-1)?.[0]).toMatchObject({
    q: 'KGH', sector: 'Mining', currency: 'all', withData: false,
    sort: [{ key: 'sector', dir: 'asc' }, { key: 'capex', dir: 'desc' }], page: 1,
  })
})
