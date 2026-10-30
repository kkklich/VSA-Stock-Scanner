import { beforeEach, expect, it, vi } from 'vitest'
import { fetchRanking } from './stocksApi'
import { apiFetchWithHeaders } from './client'

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
