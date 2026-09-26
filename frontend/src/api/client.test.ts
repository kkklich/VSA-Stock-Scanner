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
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from '../lib/authToken'

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

// ── Signed-in requests (added 2026-09-22) ─────────────────────────────────────
//
// The access token lives 30 minutes, so an open tab WILL meet an expired one.
// The wrapper answers a 401 by refreshing once and replaying the request; the
// alternative is logging someone out in the middle of a click.

describe('bearer token and silent refresh', () => {
  beforeEach(() => clearTokens())
  afterEach(() => clearTokens())

  it('sends the access token when there is one', async () => {
    setTokens('access-1', 'refresh-1')
    fetchMock.mockResolvedValue(response(200, { ok: true }))

    await apiFetch('/api/stocks/ranking')

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBe(
      'Bearer access-1',
    )
  })

  it('sends nothing when signed out', async () => {
    fetchMock.mockResolvedValue(response(200, { ok: true }))

    await apiFetch('/api/stocks/ranking')

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined()
  })

  it('refreshes once on a 401 and replays the request', async () => {
    setTokens('stale-access', 'refresh-1')
    fetchMock
      .mockResolvedValueOnce(response(401, { detail: { code: 'session_expired' } }))
      .mockResolvedValueOnce(
        response(200, { accessToken: 'fresh-access', refreshToken: 'refresh-2' }),
      )
      .mockResolvedValueOnce(response(200, { ok: true }))

    await expect(apiFetch<{ ok: boolean }>('/api/auth/me')).resolves.toEqual({
      ok: true,
    })
    // original → refresh → replay, and the replay carries the NEW token.
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1][0]).toContain('/api/auth/refresh')
    const [, replayInit] = fetchMock.mock.calls[2]
    expect((replayInit.headers as Record<string, string>).Authorization).toBe(
      'Bearer fresh-access',
    )
    expect(getAccessToken()).toBe('fresh-access')
  })

  it('gives up and forgets the session when the refresh is refused', async () => {
    setTokens('stale-access', 'dead-refresh')
    fetchMock
      .mockResolvedValueOnce(response(401, { detail: { code: 'session_expired' } }))
      .mockResolvedValueOnce(response(401, { detail: { code: 'session_expired' } }))

    await expect(apiFetch('/api/auth/me')).rejects.toMatchObject({ status: 401 })
    // Not replayed a second time, and the dead tokens are gone — otherwise
    // every later request would pay two round trips to fail.
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
  })

  it('does not try to refresh the sign-in calls themselves', async () => {
    setTokens('stale-access', 'refresh-1')
    fetchMock.mockResolvedValue(
      response(401, { detail: { code: 'bad_credentials', message: 'nope' } }),
    )

    await expect(
      apiFetch('/api/auth/login', { method: 'POST', skipAuth: true }),
    ).rejects.toMatchObject({ status: 401, code: 'bad_credentials' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reads the structured error detail the auth endpoints send', async () => {
    fetchMock.mockResolvedValue(
      response(409, {
        detail: { code: 'email_taken', message: 'That address already has an account.' },
      }),
    )

    await expect(
      apiFetch('/api/auth/register', { method: 'POST', skipAuth: true }),
    ).rejects.toMatchObject({
      status: 409,
      code: 'email_taken',
      message: 'That address already has an account.',
    })
  })
})
