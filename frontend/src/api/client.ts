// Base fetch wrapper used by all API functions.
// In development the Vite proxy forwards /api → http://localhost:5111,
// so no absolute URL is needed. In production set VITE_API_URL to the
// backend origin (e.g. https://api.stockpilot.pl).

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from '../lib/authToken'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

/** Our own options on top of fetch's.
 *
 *  `skipAuth` is for the sign-in calls themselves: sending a stale (or
 *  expired) bearer token to /api/auth/login would be pointless, and sending it
 *  to /api/auth/refresh would make a 401 there look like an expired session
 *  rather than a bad refresh token. */
export interface ApiRequestInit extends RequestInit {
  skipAuth?: boolean
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /** Stable machine-readable cause, when the endpoint sends one (the
     *  /api/auth/* endpoints do, so the sign-in screen can show the message in
     *  the visitor's own language instead of the API's English). */
    public readonly code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Status 0 = the request never reached a server (connection refused, DNS,
 *  offline). Distinct from a real HTTP status so callers can tell the two
 *  apart. */
const NETWORK_ERROR_STATUS = 0

/** Statuses that mean "the backend is not answering *yet*", not "your request
 *  was wrong": the dev proxy's own 503 when Uvicorn is not listening, plus the
 *  gateway codes a production Nginx returns while the API container restarts. */
const RETRYABLE_STATUSES = new Set([502, 503, 504])

/** Backoff before each retry, in ms. The backend launcher starts PostgreSQL
 *  and installs dependencies before Uvicorn binds the port, so a cold start can
 *  take a while — these five attempts span ~15s, which covers the gap without
 *  making a genuine failure feel hung. */
const RETRY_DELAYS_MS = [500, 1_000, 2_000, 4_000, 8_000]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** Only idempotent reads may be retried — replaying a POST could trigger a
 *  second data refresh. */
function isRetryableRequest(init?: RequestInit): boolean {
  const method = (init?.method ?? 'GET').toUpperCase()
  return method === 'GET' || method === 'HEAD'
}

/** The signed-in visitor's bearer token, when there is one. */
function authHeaders(init?: ApiRequestInit): Record<string, string> {
  if (init?.skipAuth) return {}
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** In-flight refresh, shared by every request that hits a 401 at once.
 *
 *  Without this, a page that fires six requests on load would send six refresh
 *  calls the moment the access token expires — and five of them would race to
 *  overwrite the stored tokens. */
let refreshInFlight: Promise<boolean> | null = null

/** Exchange the refresh token for a new access token. True when it worked.
 *
 *  Done with a plain fetch rather than through `apiFetch` on purpose: this
 *  module is what `authApi` is built on, so calling back into it would be a
 *  circular import — and a refresh must never itself try to refresh. */
async function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({}),
        })
        if (!response.ok) {
          // The refresh token is expired or was invalidated by a password
          // change: this session is genuinely over.
          if (response.status === 401 || response.status === 403) clearTokens()
          return false
        }
        const body = (await response.json()) as {
          accessToken?: string
          refreshToken?: string
        }
        if (!body.accessToken) return false
        setTokens(body.accessToken, body.refreshToken)
        return true
      } catch {
        // Network failure — keep the tokens; the next attempt may succeed.
        return false
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

async function requestOnce<T>(
  path: string,
  init?: ApiRequestInit,
): Promise<{ data: T; headers: Headers }> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(init),
        ...init?.headers,
      },
    })
  } catch (err) {
    // fetch() rejects (TypeError "Failed to fetch") when no server answered.
    // Turn that into an ApiError so every caller has one error shape to handle
    // and the UI can show something better than "Failed to fetch".
    throw new ApiError(
      NETWORK_ERROR_STATUS,
      err instanceof Error && err.name === 'AbortError'
        ? 'Request cancelled.'
        : 'Cannot reach the StockPilot API. Is the backend running (run-backend-python.bat, port 5111)?',
    )
  }

  if (!response.ok) {
    let message = `HTTP ${response.status}`
    let code: string | undefined
    try {
      const body = await response.json()
      const detail = body?.detail
      if (detail && typeof detail === 'object') {
        // FastAPI allows a structured `detail`. The sign-in endpoints use
        // { code, message }; /health uses { status, db }. Taking `message`
        // when there is one keeps a rendered error from becoming
        // "[object Object]".
        code = typeof detail.code === 'string' ? detail.code : undefined
        message = detail.message ?? body?.message ?? message
      } else {
        message = detail ?? body?.message ?? message
      }
    } catch {
      // non-JSON error body — keep the default
    }
    throw new ApiError(response.status, message, code)
  }

  const data = (await response.json()) as T
  return { data, headers: response.headers }
}

/** Like {@link apiFetch} but also returns the raw response headers — needed by
 *  endpoints that carry pagination metadata (e.g. `X-Total-Count`).
 *
 *  Retries while the backend is unreachable so the app heals itself instead of
 *  showing a dead error page: the frontend dev server is ready in seconds while
 *  the backend is still booting, and a user who opens the page in that window
 *  would otherwise have to reload by hand. */
export async function apiFetchWithHeaders<T>(
  path: string,
  init?: ApiRequestInit,
): Promise<{ data: T; headers: Headers }> {
  const retryable = isRetryableRequest(init)
  // One silent re-authentication per request: the access token lives 30
  // minutes, so an open tab WILL meet an expired one. Refreshing and replaying
  // the call is what keeps "stay signed in" from meaning "be logged out
  // mid-click". Only once — if the replay is refused too, the session is over
  // and the error belongs to the caller.
  let mayRefresh = !init?.skipAuth && Boolean(getAccessToken())

  for (let attempt = 0; ; attempt++) {
    try {
      return await requestOnce<T>(path, init)
    } catch (err) {
      const isApiError = err instanceof ApiError

      if (isApiError && err.status === 401 && mayRefresh) {
        mayRefresh = false
        if (await refreshAccessToken()) {
          attempt -= 1 // the refresh is not one of the backoff attempts
          continue
        }
      }

      const canRetry =
        retryable &&
        attempt < RETRY_DELAYS_MS.length &&
        isApiError &&
        (err.status === NETWORK_ERROR_STATUS || RETRYABLE_STATUSES.has(err.status)) &&
        // An aborted request was cancelled on purpose (component unmounted,
        // ticker switched) — never retry it.
        init?.signal?.aborted !== true &&
        err.message !== 'Request cancelled.'

      if (!canRetry) throw err

      await sleep(RETRY_DELAYS_MS[attempt])
    }
  }
}

export async function apiFetch<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const { data } = await apiFetchWithHeaders<T>(path, init)
  return data
}
