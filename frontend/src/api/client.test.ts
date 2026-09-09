// Retry policy of the shared fetch wrapper.
//
// The wrapper retries so the app heals itself while the backend is still
// booting: the frontend dev server is ready in seconds, Uvicorn is not, and a
// user who opens the page in that window would otherwise see a dead error page.
//
// The flip side is that anything WRONGLY marked retryable costs the user the
// full ~15-second backoff and asks the backend the same question six times.
// That is what "this stock has no intraday data" used to do: the backend
// answered 502, so the app treated a settled fact as an outage. It now answers
// 404, and this file pins the fact that 404 stops immediately.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, apiFetchWithHeaders, ApiError } from './client'

/** A minimal stand-in for the parts of Response the wrapper reads. */
function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: new Headers({ 'X-Total-Count': '7' }),
  } as unknown as Response
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('apiFetch retry policy', () => {
  it('does not retry a 404 and reports the backend’s own message', async () => {
    fetchMock.mockResolvedValue(
      response(404, { detail: 'No 30m intraday data is available for TST.' }),
    )

    await expect(apiFetch('/api/stocks/tst/signals?interval=30m')).rejects.toMatchObject({
      status: 404,
      message: 'No 30m intraday data is available for TST.',
    })
    // Asked once. Retrying would ask Yahoo the same settled question six times
    // and make the user wait ~15 seconds to be told something knowable at once.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not retry other client errors either', async () => {
    fetchMock.mockResolvedValue(response(400, { detail: 'Unknown interval' }))

    await expect(apiFetch('/api/stocks/tst/signals?interval=5m')).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries a 502 — the backend really may not be up yet', async () => {
    vi.useFakeTimers()
    fetchMock
      .mockResolvedValueOnce(response(502, { detail: 'gateway' }))
      .mockResolvedValueOnce(response(200, { ok: true }))

    const pending = apiFetch<{ ok: boolean }>('/api/stocks/ranking')
    await vi.advanceTimersByTimeAsync(600)

    await expect(pending).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('retries when no server answered at all', async () => {
    vi.useFakeTimers()
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(response(200, { ok: true }))

    const pending = apiFetch<{ ok: boolean }>('/api/stocks/ranking')
    await vi.advanceTimersByTimeAsync(600)

    await expect(pending).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('never replays a POST — a second refresh is not a free retry', async () => {
    fetchMock.mockResolvedValue(response(502, { detail: 'gateway' }))

    await expect(
      apiFetch('/api/stocks/refresh', { method: 'POST' }),
    ).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('gives up after the backoff is exhausted', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValue(response(503, { detail: 'starting' }))

    const pending = apiFetch('/api/stocks/ranking')
    const assertion = expect(pending).rejects.toMatchObject({ status: 503 })
    await vi.advanceTimersByTimeAsync(20_000)
    await assertion

    expect(fetchMock).toHaveBeenCalledTimes(6) // first attempt + five retries
  })

  it('passes response headers through for the paginated endpoints', async () => {
    fetchMock.mockResolvedValue(response(200, []))

    const { headers } = await apiFetchWithHeaders('/api/stocks/ranking')
    expect(headers.get('X-Total-Count')).toBe('7')
  })
})
