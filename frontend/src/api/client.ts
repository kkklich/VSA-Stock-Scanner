// Base fetch wrapper used by all API functions.
// In development the Vite proxy forwards /api → http://localhost:5111,
// so no absolute URL is needed. In production set VITE_API_URL to the
// backend origin (e.g. https://api.stockpilot.pl).

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
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

async function requestOnce<T>(
  path: string,
  init?: RequestInit,
): Promise<{ data: T; headers: Headers }> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
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
    try {
      const body = await response.json()
      message = body?.detail ?? body?.message ?? message
    } catch {
      // non-JSON error body — keep the default
    }
    throw new ApiError(response.status, message)
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
  init?: RequestInit,
): Promise<{ data: T; headers: Headers }> {
  const retryable = isRetryableRequest(init)

  for (let attempt = 0; ; attempt++) {
    try {
      return await requestOnce<T>(path, init)
    } catch (err) {
      const isApiError = err instanceof ApiError
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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { data } = await apiFetchWithHeaders<T>(path, init)
  return data
}
