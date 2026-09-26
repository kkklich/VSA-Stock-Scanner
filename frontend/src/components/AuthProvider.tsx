// The provider that holds the session for the whole app (the context and the
// useAuth hook live in hooks/useAuth.ts).
//
// One provider at the root (main.tsx) holds it so the top bar, the
// sign-in page and the settings page all read the same state. Signing in is
// OPTIONAL on this site: every page works signed out, and this context simply
// reports `user: null` then.
//
// On load it asks the backend twice, both cheap:
//   * /api/auth/config — are accounts available here at all? (A deployment
//     without a database has nowhere to store them, and the UI then hides the
//     sign-in button rather than offering a form that can only fail.)
//   * /api/auth/me     — only when a token is stored, to confirm it still
//     works. A token can be stale: the password may have been changed
//     elsewhere, or a backend without a configured JWT secret may have
//     restarted. The client's own refresh retry covers a merely expired one.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import {
  changePassword as apiChangePassword,
  fetchAuthConfig,
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  type AuthConfig,
  type AuthSession,
  type AuthUser,
} from '../api/authApi'
import { AuthContext } from '../hooks/useAuth'
import {
  clearTokens,
  getAccessToken,
  onTokensChanged,
  setTokens,
} from '../lib/authToken'

/** A deployment we have not heard from yet: assume accounts work, so the
 *  sign-in button does not flicker away on a slow first answer. */
const ASSUMED_CONFIG: AuthConfig = {
  enabled: true,
  registrationOpen: true,
  persistentSessions: true,
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [loading, setLoading] = useState(true)

  // Restore the session stored in this browser, if any.
  useEffect(() => {
    let cancelled = false

    async function restore() {
      try {
        const deploymentConfig = await fetchAuthConfig()
        if (!cancelled) setConfig(deploymentConfig)
        if (!deploymentConfig.enabled) {
          if (!cancelled) setUser(null)
          return
        }
      } catch {
        // An older backend has no /api/auth/config. Assume accounts work and
        // let the sign-in attempt itself report the truth.
        if (!cancelled) setConfig(ASSUMED_CONFIG)
      }

      if (!getAccessToken()) return
      try {
        const me = await fetchMe()
        if (!cancelled) setUser(me)
      } catch (err) {
        // 401 means the stored token is no longer good (password changed, or
        // the backend restarted without a JWT secret): forget it quietly.
        // Anything else is a backend problem, not a sign-out — keep the token
        // so the session survives a restarting API.
        if (err instanceof ApiError && err.status === 401) clearTokens()
      }
    }

    restore().finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Another tab signing out (or the API client giving up on a dead refresh
  // token) clears the store — follow it, so two open tabs never disagree.
  useEffect(
    () =>
      onTokensChanged(() => {
        if (!getAccessToken()) setUser(null)
      }),
    [],
  )

  const adopt = useCallback((session: AuthSession) => {
    setTokens(session.accessToken, session.refreshToken)
    setUser(session.user)
  }, [])

  const signIn = useCallback(
    async (email: string, password: string) => {
      adopt(await apiLogin(email, password))
    },
    [adopt],
  )

  const signUp = useCallback(
    async (email: string, password: string, displayName?: string) => {
      adopt(await apiRegister(email, password, displayName))
    },
    [adopt],
  )

  const signOut = useCallback(() => {
    // Clear the HttpOnly refresh cookie on the backend, and drop local tokens.
    apiLogout().catch(() => {
      // Ignore network failures on sign-out
    })
    clearTokens()
    setUser(null)
  }, [])

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      // The backend invalidates the old tokens, so it returns fresh ones —
      // without adopting them the visitor would be signed out by their own
      // password change.
      adopt(await apiChangePassword(currentPassword, newPassword))
    },
    [adopt],
  )

  const value = useMemo(
    () => ({ user, loading, config, signIn, signUp, signOut, changePassword }),
    [user, loading, config, signIn, signUp, signOut, changePassword],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
