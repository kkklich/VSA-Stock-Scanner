// Who is signed in, for the whole app.
//
// This file holds the context and the hook; the provider that fills it is
// components/AuthProvider.tsx (kept apart so this module exports no component
// and the dev server's fast refresh keeps working).
//
// Signing in is OPTIONAL on this site: every page works signed out, and this
// context simply reports `user: null` then.

import { createContext, useContext } from 'react'
import type { AuthConfig, AuthUser } from '../api/authApi'

export interface AuthContextValue {
  /** The signed-in account, or null when nobody is. */
  user: AuthUser | null
  /** True until the stored session has been checked — avoids a "Sign in"
   *  button flashing for someone who is in fact already signed in. */
  loading: boolean
  /** What the deployment supports. Null until /api/auth/config answers. */
  config: AuthConfig | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, displayName?: string) => Promise<void>
  signOut: () => void
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context) return context
  // Rendered outside the provider (a unit test mounting one component): report
  // "signed out, accounts available" rather than crashing the tree.
  return {
    user: null,
    loading: false,
    config: null,
    signIn: async () => {},
    signUp: async () => {},
    signOut: () => {},
    changePassword: async () => {},
  }
}
