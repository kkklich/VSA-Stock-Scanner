// Turning a failed sign-in into a sentence the visitor can read.
//
// The backend answers with a stable `code` next to its English message (see
// app/routers/auth.py `_fail`), so the sign-in screen can speak Polish to a
// Polish visitor. An unknown code falls back to the server's own message,
// which is always better than a generic "something went wrong".

import type { TFunction } from 'i18next'
import { ApiError } from '../api/client'

/** The codes the UI has its own wording for. Anything else falls back. */
const TRANSLATED = new Set([
  'bad_credentials',
  'email_taken',
  'weak_password',
  'invalid_email',
  'too_many_attempts',
  'registration_closed',
  'accounts_unavailable',
  'wrong_current_password',
  'session_expired',
  'not_signed_in',
  'admin_token_required',
  'account_not_found',
])

export function authErrorMessage(err: unknown, t: TFunction): string {
  if (err instanceof ApiError) {
    if (err.code && TRANSLATED.has(err.code)) return t(`auth.errors.${err.code}`)
    // The API never answered (offline, backend down): client.ts already put a
    // readable sentence on it, but it is English — say it in the UI's language.
    if (err.status === 0) return t('auth.errors.offline')
    if (err.message) return err.message
  }
  if (err instanceof Error && err.message) return err.message
  return t('auth.errorGeneric')
}
