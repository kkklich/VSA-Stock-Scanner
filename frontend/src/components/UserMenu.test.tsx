// The sign-in control in the top bar, and the token store behind it.

import { describe, expect, it, beforeEach, vi } from 'vitest'
import { screen, renderWithProviders } from '../test/utils'
import { UserMenu } from './UserMenu'
import { initialsOf } from '../lib/format'
import { AuthProvider } from './AuthProvider'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from '../lib/authToken'

describe('initialsOf', () => {
  it('uses the first and last word of a display name', () => {
    expect(initialsOf('Krzysztof Klich', 'k@example.com')).toBe('KK')
  })

  it('falls back to two letters of a single word', () => {
    expect(initialsOf('ala', 'ala@example.com')).toBe('AL')
  })

  it('uses the e-mail when there is no display name', () => {
    expect(initialsOf('   ', 'ola.nowak@example.com')).toBe('ON')
  })
})

describe('the token store', () => {
  beforeEach(() => clearTokens())

  it('remembers the access token and leaves refresh tokens to HttpOnly cookies', () => {
    setTokens('access-1', 'refresh-1')
    expect(getAccessToken()).toBe('access-1')
    // Refresh tokens are never stored in localStorage — they live in HttpOnly cookies
    expect(getRefreshToken()).toBe('')
    expect(window.localStorage.getItem('stockpilot:auth:refreshToken')).toBeNull()
    clearTokens()
    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
  })

  it('survives storage being blocked (private mode)', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    try {
      expect(() => setTokens('a', 'b')).not.toThrow()
      expect(getAccessToken()).toBe('')
    } finally {
      spy.mockRestore()
    }
  })
})

describe('UserMenu', () => {
  beforeEach(() => {
    clearTokens()
    vi.restoreAllMocks()
  })

  it('offers a sign-in link when nobody is signed in', () => {
    // No stored token, so the provider asks /api/auth/config and nothing else.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            enabled: true,
            registrationOpen: true,
            persistentSessions: true,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    renderWithProviders(
      <AuthProvider>
        <UserMenu />
      </AuthProvider>,
    )

    return screen.findByRole('link', { name: /sign in|zaloguj/i })
  })

  it('shows nothing to sign in to when the deployment has no accounts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            enabled: false,
            registrationOpen: false,
            persistentSessions: false,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )

    const { container } = renderWithProviders(
      <AuthProvider>
        <UserMenu />
      </AuthProvider>,
    )

    // Once the config answers "no accounts here", the control disappears
    // rather than offering a form that could only fail.
    await vi.waitFor(() => expect(container.querySelector('a')).toBeNull())
  })
})
