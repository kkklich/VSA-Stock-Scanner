import { beforeEach, expect, it, vi } from 'vitest'
import { fetchInsiderTransactions, fetchRanking } from './stocksApi'
import { apiFetch, apiFetchWithHeaders } from './client'

vi.mock('./client', () => ({ apiFetchWithHeaders: vi.fn(), apiFetch: vi.fn() }))

beforeEach(() => {
  vi.mocked(apiFetchWithHeaders).mockResolvedValue({ data: [], headers: new Headers() })
})

it('serializes insider criteria including an explicit zero threshold', async () => {
  await fetchRanking({ insiderActivity: 'netBuy', insiderDays: 365, minInsiderValue: 0 })
  const url = new URL(vi.mocked(apiFetchWithHeaders).mock.lastCall![0], 'https://example.test')
  expect(url.searchParams.get('insiderActivity')).toBe('netBuy')
  expect(url.searchParams.get('insiderDays')).toBe('365')
  expect(url.searchParams.get('minInsiderValue')).toBe('0')
})

it('omits inactive insider criteria', async () => {
  await fetchRanking({ insiderActivity: 'all' })
  const url = vi.mocked(apiFetchWithHeaders).mock.lastCall![0]
  expect(url).not.toContain('insider')
  expect(url).not.toContain('Insider')
})

it('serializes insider sorting with its reporting window and tie-break', async () => {
  await fetchRanking({
    insiderDays: 180, insiderEnd: '2025-06-01',
    sort: [{ key: 'insiderValueLast30Days', dir: 'desc' }, { key: 'ticker', dir: 'asc' }],
  })
  const url = new URL(vi.mocked(apiFetchWithHeaders).mock.lastCall![0], 'https://example.test')
  expect(url.searchParams.get('sortBy')).toBe('insiderValueLast30Days,ticker')
  expect(url.searchParams.get('sortDir')).toBe('desc,asc')
  expect(url.searchParams.get('insiderDays')).toBe('180')
  expect(url.searchParams.get('insiderEnd')).toBe('2025-06-01')
})

it('requests a fresh ESPI fetch only on explicit refresh', async () => {
  await fetchInsiderTransactions('CBF', { refresh: true, includeAll: true })
  expect(apiFetch).toHaveBeenLastCalledWith(
    '/api/stocks/CBF/insider-transactions?includeAll=true&refresh=true',
  )
  await fetchInsiderTransactions('PKO')
  expect(apiFetch).toHaveBeenLastCalledWith('/api/stocks/PKO/insider-transactions')
})
