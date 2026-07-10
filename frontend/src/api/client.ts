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

/** Like {@link apiFetch} but also returns the raw response headers — needed by
 *  endpoints that carry pagination metadata (e.g. `X-Total-Count`). */
export async function apiFetchWithHeaders<T>(
  path: string,
  init?: RequestInit,
): Promise<{ data: T; headers: Headers }> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { data } = await apiFetchWithHeaders<T>(path, init)
  return data
}
