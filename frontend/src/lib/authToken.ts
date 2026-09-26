// Where the signed-in visitor's tokens live in the browser.
//
// Two tokens, as the backend issues them (app/services/auth.py):
//   * access token  — short-lived (30 min), kept in localStorage and sent on
//     every API request
//   * refresh token — long-lived (30 days), stored in an HttpOnly cookie
//     (never in localStorage), sent by the browser to /api/auth/refresh to
//     get a new access token.
//
// Storing the refresh token in an HttpOnly cookie protects against token theft
// via XSS, while the short-lived access token is retained in localStorage to
// survive page reloads and tab closures.

const ACCESS_KEY = 'stockpilot:auth:accessToken'
const LEGACY_REFRESH_KEY = 'stockpilot:auth:refreshToken'

// Clean up any legacy refresh token remaining in localStorage from prior versions
try {
  window.localStorage.removeItem(LEGACY_REFRESH_KEY)
} catch {
  // Storage blocked: private browsing mode
}

/** Notified whenever the stored tokens change, so the UI can re-render. */
type Listener = () => void
const listeners = new Set<Listener>()

function read(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function write(key: string, value: string): void {
  try {
    if (value) window.localStorage.setItem(key, value)
    else window.localStorage.removeItem(key)
  } catch {
    // Storage blocked: the session then lasts until the tab is closed, which
    // is a degraded experience rather than a broken one.
  }
}

export function getAccessToken(): string {
  return read(ACCESS_KEY)
}

/** Refresh tokens are now stored exclusively in HttpOnly cookies. */
export function getRefreshToken(): string {
  return ''
}

export function setTokens(accessToken: string, _refreshToken?: string): void {
  write(ACCESS_KEY, accessToken)
  try {
    window.localStorage.removeItem(LEGACY_REFRESH_KEY)
  } catch {
    // ignore
  }
  listeners.forEach((listener) => listener())
}

export function clearTokens(): void {
  write(ACCESS_KEY, '')
  try {
    window.localStorage.removeItem(LEGACY_REFRESH_KEY)
  } catch {
    // ignore
  }
  listeners.forEach((listener) => listener())
}

export function onTokensChanged(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
