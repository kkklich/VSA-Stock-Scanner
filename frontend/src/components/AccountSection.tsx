// The Account section of the Settings page: who is signed in, and the one
// thing an account holder can do to it today — change the password.
//
// There is no "reset my password by e-mail" anywhere in the app, because the
// app sends no e-mail yet (agent/ROADMAP.md #30). That makes this form the
// only way a password changes, so it asks for the current one.

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Check, Loader2, LogIn, LogOut } from 'lucide-react'
import { authErrorMessage } from '../lib/authErrors'
import { useAuth } from '../hooks/useAuth'

const FIELD =
  'w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500/60 focus:outline-none'

export function AccountSection() {
  const { t } = useTranslation()
  const { user, config, signOut, changePassword } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  // No accounts on this deployment (no database) — say nothing at all.
  if (config && !config.enabled) return null

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setDone(false)
    setBusy(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setDone(true)
    } catch (err) {
      setError(authErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 sm:p-5">
      <h2 className="text-sm font-semibold text-slate-200">{t('auth.account')}</h2>

      {!user ? (
        <>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-slate-500">
            {t('auth.signedOutHint')}
          </p>
          <Link
            to="/login"
            className="mt-4 inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
          >
            <LogIn size={14} aria-hidden />
            {t('auth.signIn')}
          </Link>
        </>
      ) : (
        <>
          <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-[8rem_1fr]">
            <dt className="text-slate-500">{t('auth.displayName')}</dt>
            <dd className="text-slate-200">{user.displayName}</dd>
            <dt className="text-slate-500">{t('auth.email')}</dt>
            <dd className="break-all text-slate-200">{user.email}</dd>
          </dl>

          <form onSubmit={onSubmit} className="mt-5 flex max-w-sm flex-col gap-3">
            <h3 className="text-xs font-semibold text-slate-300">
              {t('auth.changePassword')}
            </h3>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-slate-500">
                {t('auth.currentPassword')}
              </span>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className={FIELD}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-slate-500">{t('auth.newPassword')}</span>
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className={FIELD}
              />
              <span className="text-[11px] text-slate-500">
                {t('auth.passwordRule')}
              </span>
            </label>

            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-2.5 text-xs leading-relaxed text-rose-300"
              >
                <AlertCircle size={15} className="mt-px shrink-0" aria-hidden />
                {error}
              </p>
            )}
            {done && (
              <p className="flex items-center gap-2 text-xs text-emerald-400">
                <Check size={15} aria-hidden />
                {t('auth.passwordChanged')}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={busy}
                className="flex items-center gap-2 rounded-md bg-emerald-500/90 px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy && <Loader2 size={14} className="animate-spin" aria-hidden />}
                {t('auth.changePassword')}
              </button>
              <button
                type="button"
                onClick={signOut}
                className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-800/60 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
              >
                <LogOut size={14} aria-hidden />
                {t('auth.signOut')}
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  )
}
