import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './client'
import { importXtb, previewXtb } from './portfoliosApi'

vi.mock('./client', () => ({ apiFetch: vi.fn() }))
beforeEach(() => vi.resetAllMocks())

describe('XTB report uploads', () => {
  it('sends the original file as a binary body with an encoded filename and abort signal', async () => {
    const file = new File(['report'], 'Historia XTB & PLN.xlsx')
    const signal = new AbortController().signal
    await previewXtb('portfolio-1', file, signal)
    const [path, request] = vi.mocked(apiFetch).mock.calls[0]
    const url = new URL(path, 'https://example.com')
    expect(url.pathname).toBe('/api/portfolios/portfolio-1/imports/xtb/preview')
    expect(url.searchParams.get('filename')).toBe(file.name)
    expect(request).toEqual({ method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file, signal })
  })

  it('includes the preview version and explicit partial-import choice when committing', async () => {
    const file = new File(['report'], 'history.csv')
    const signal = new AbortController().signal
    await importXtb('portfolio-1', file, 7, true, signal)
    const url = new URL(vi.mocked(apiFetch).mock.calls[0][0], 'https://example.com')
    expect(url.pathname).toBe('/api/portfolios/portfolio-1/imports/xtb')
    expect(url.searchParams.get('version')).toBe('7')
    expect(url.searchParams.get('allow_partial')).toBe('true')
  })
})
