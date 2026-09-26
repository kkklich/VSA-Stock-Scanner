// Sign-in endpoints (backend: app/routers/auth.py).
//
// Accounts are optional: the whole site is readable signed out, and these calls
// exist so a visitor CAN have an account, not so the app can demand one.

import { apiFetch } from './client'

export interface AuthUser {
  id: number
  email: string
  displayName: string
  role: string
  emailVerified: boolean
  createdAt: string
  lastLoginAt: string | null
}

export interface AuthSession {
  accessToken: string
  refreshToken?: string
  tokenType: string
  /** Seconds until the access token expires. */
  expiresIn: number
  user: AuthUser
}

export interface AuthConfig {
  /** False when the deployment has no database — accounts cannot be stored. */
  enabled: boolean
  registrationOpen: boolean
  /** False means a backend restart signs everyone out (no JWT secret set). */
  persistentSessions: boolean
}

/** POST with a JSON body, without the Authorization header (see client.ts). */
function post<T>(path: string, body: unknown, skipAuth = true): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
    ...(skipAuth ? { skipAuth: true } : {}),
  })
}

export function fetchAuthConfig(): Promise<AuthConfig> {
  return apiFetch<AuthConfig>('/api/auth/config', { skipAuth: true })
}

export function register(
  email: string,
  password: string,
  displayName?: string,
): Promise<AuthSession> {
  return post<AuthSession>('/api/auth/register', { email, password, displayName })
}

export function login(email: string, password: string): Promise<AuthSession> {
  return post<AuthSession>('/api/auth/login', { email, password })
}

export function refreshSession(refreshToken?: string): Promise<AuthSession> {
  return post<AuthSession>(
    '/api/auth/refresh',
    refreshToken ? { refreshToken } : {},
  )
}

export function logout(): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>('/api/auth/logout', {})
}

/** Who is signed in. Sends the access token (no `skipAuth`). */
export function fetchMe(): Promise<AuthUser> {
  return apiFetch<AuthUser>('/api/auth/me')
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<AuthSession> {
  return post<AuthSession>(
    '/api/auth/change-password',
    { currentPassword, newPassword },
    false,
  )
}
