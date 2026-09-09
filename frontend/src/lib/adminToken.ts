// The optional admin token for /api/admin/*.
//
// The backend leaves those endpoints open when STOCKPILOT_ADMIN_TOKEN is unset
// (right for a laptop) and requires an `X-Admin-Token` header when it is set
// (right for a public deployment — the System page shows stack traces, file
// paths and visitor IP addresses). The owner pastes the token once on the
// System page and it is remembered in this browser.
//
// This is a shared operator secret, not a user account: it is stored in
// localStorage exactly like the theme choice, and it never leaves the browser
// except as the header on an admin request.

const STORAGE_KEY = 'stockpilot:adminToken'

export function getAdminToken(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    // Private mode / storage blocked — behave as if no token were stored.
    return ''
  }
}

export function setAdminToken(token: string): void {
  try {
    const trimmed = token.trim()
    if (trimmed) window.localStorage.setItem(STORAGE_KEY, trimmed)
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing to do: the token simply will not be remembered.
  }
}
