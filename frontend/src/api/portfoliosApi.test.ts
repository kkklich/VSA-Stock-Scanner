import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './client'
import { importXtb, importXtbWallets, portfolioRequest, previewXtb, previewXtbWallets } from './portfoliosApi'

vi.mock('./client', () => ({ apiFetch: vi.fn() }))
beforeEach(() => vi.resetAllMocks())

it('carries the account shown in the portfolio page on reads and writes', async () => {
  const signal = new AbortController().signal
  await portfolioRequest('GET', '', undefined, signal, 17)
  await portfolioRequest('GET', '/instruments', undefined, signal, 17)
  await portfolioRequest('PATCH', '/portfolio-1', { name: 'Retirement' }, signal, 17)
  const headers = { 'X-Expected-User-Id': '17' }
  expect(apiFetch).toHaveBeenNthCalledWith(1, '/api/portfolios', { method: 'GET', headers, signal })
  expect(apiFetch).toHaveBeenNthCalledWith(2, '/api/portfolios/instruments', { method: 'GET', headers, signal })
  expect(apiFetch).toHaveBeenNthCalledWith(3, '/api/portfolios/portfolio-1', {
    method: 'PATCH', headers, signal, body: JSON.stringify({ name: 'Retirement' }),
  })
})

describe('XTB report uploads', () => {
  it('sends the original file as a binary body with an encoded filename and abort signal', async () => {
    const file = new File(['report'], 'Historia XTB & PLN.xlsx')
    const signal = new AbortController().signal
    await previewXtb('portfolio-1', file, signal, 17)
    const [path, request] = vi.mocked(apiFetch).mock.calls[0]
    const url = new URL(path, 'https://example.com')
    expect(url.pathname).toBe('/api/portfolios/portfolio-1/imports/xtb/preview')
    expect(url.searchParams.get('filename')).toBe(file.name)
    expect(request).toEqual({ method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Expected-User-Id': '17' }, body: file, signal })
  })

  it('includes the preview version and explicit partial-import choice when committing', async () => {
    const file = new File(['report'], 'history.csv')
    const signal = new AbortController().signal
    await importXtb('portfolio-1', file, 7, true, signal, 17)
    const [path, request] = vi.mocked(apiFetch).mock.calls[0]
    const url = new URL(path, 'https://example.com')
    expect(url.pathname).toBe('/api/portfolios/portfolio-1/imports/xtb')
    expect(url.searchParams.get('version')).toBe('7')
    expect(url.searchParams.get('allow_partial')).toBe('true')
    expect(request?.headers).toMatchObject({ 'X-Expected-User-Id': '17' })
  })

  it('binds worksheet uploads to the account and saves using the preview token', async () => {
    const file = new File(['report'], 'Historia XTB & IKE.xlsx')
    const signal = new AbortController().signal
    await previewXtbWallets(file, 17, signal)
    await importXtbWallets(file, 17, 'reviewed-plan', true, signal)
    const [previewPath, request] = vi.mocked(apiFetch).mock.calls[0]
    const previewUrl = new URL(previewPath, 'https://example.com')
    const [commitPath, commitRequest] = vi.mocked(apiFetch).mock.calls[1]
    const commitUrl = new URL(commitPath, 'https://example.com')
    expect(previewUrl.pathname).toBe('/api/portfolios/imports/xtb/wallets/preview')
    expect(commitUrl.pathname).toBe('/api/portfolios/imports/xtb/wallets')
    expect(previewUrl.searchParams.get('filename')).toBe(file.name)
    expect(previewUrl.searchParams.has('import_id')).toBe(false)
    expect(commitUrl.searchParams.has('import_id')).toBe(false)
    expect(commitUrl.searchParams.get('allow_partial')).toBe('true')
    const headers = { 'Content-Type': 'application/octet-stream', 'X-Expected-User-Id': '17' }
    expect(request).toEqual({ method: 'POST', headers, body: file, signal })
    expect(commitRequest).toEqual({ method: 'POST', headers: { ...headers, 'X-XTB-Preview': 'reviewed-plan' }, body: file, signal })
  })
})
