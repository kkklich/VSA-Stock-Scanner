// Sign in / create an account.
//
// It lives inside the normal app shell (sidebar, top bar, footer) rather than
// as a full-screen gate, because the site is public: nothing here is required
// to read the rankings, the charts or the scanners. An account is somewhere to
// keep what is yours.
//
// One page, two modes, so somebody who came to register does not have to find
// a second screen. Anyone may create an account.
//
// No "forgot my password" link on purpose: this app sends no e-mail yet, so
// such a link would lead nowhere. A signed-in visitor can change their
// password in Settings (see agent/ROADMAP.md #30).

import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertCircle, Loader2, LogIn, UserPlus } from 'lucide-react'
import { authErrorMessage } from '../lib/authErrors'
import { useAuth } from '../hooks/useAuth'

type Mode = 'signin' | 'signup'

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, config, signIn, signUp } = useAuth()

  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Where to go afterwards: back where the visitor pressed "Sign in".
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  // Already signed in (or just signed in) — this page has nothing to offer.
  useEffect(() => {
    if (user) navigate(from, { replace: true })
  }, [user, from, navigate])

  const accountsUnavailable = config?.enabled === false
  const registrationClosed = config?.registrationOpen === false

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'signin') await signIn(email, password)
      else await signUp(email, password, displayName || undefined)
      // The effect above navigates once the user lands in the context.
    } catch (err) {
      setError(authErrorMessage(err, t))
    } finally {
      setBusy(false)
    }
  }

  const tabClass = (active: boolean) =>
    'flex-1 rounded-md px-3 py-2 text-xs font-semibold transition-colors ' +
    (active
      ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/40'
      : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200')

  const fieldClass =
    'w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-emerald-500/60 focus:outline-none'

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4 p-4 sm:p-6">
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <h2 className="text-sm font-semibold text-slate-200">
          {mode === 'signin' ? t('auth.signInTitle') : t('auth.signUpTitle')}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          {t('auth.optionalHint')}
        </p>

        {accountsUnavailable ? (
          <p className="mt-4 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-300">
            <AlertCircle size={15} className="mt-px shrink-0" aria-hidden />
            {t('auth.unavailable')}
          </p>
        ) : (
          <>
            <div className="mt-4 flex gap-1 rounded-lg border border-slate-800 bg-slate-950/60 p-1">
              <button
                type="button"
                onClick={() => {
                  setMode('signin')
                  setError(null)
                }}
                aria-pressed={mode === 'signin'}
                className={tabClass(mode === 'signin')}
              >
                {t('auth.signIn')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode('signup')
                  setError(null)
                }}
                aria-pressed={mode === 'signup'}
                disabled={registrationClosed}
                className={
                  tabClass(mode === 'signup') +
                  (registrationClosed ? ' cursor-not-allowed opacity-50' : '')
                }
              >
                {t('auth.createAccount')}
              </button>
            </div>

            <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-slate-400">
                  {t('auth.email')}
                </span>
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ty@example.com"
                  className={fieldClass}
                />
              </label>

              {mode === 'signup' && (
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-slate-400">
                    {t('auth.displayName')}{' '}
                    <span className="text-slate-600">{t('auth.optional')}</span>
                  </span>
                  <input
                    type="text"
                    autoComplete="nickname"
                    maxLength={80}
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className={fieldClass}
                  />
                </label>
              )}

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-slate-400">
                  {t('auth.password')}
                </span>
                <input
                  type="password"
                  required
                  minLength={mode === 'signup' ? 8 : undefined}
                  autoComplete={
                    mode === 'signup' ? 'new-password' : 'current-password'
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={fieldClass}
                />
                {mode === 'signup' && (
                  <span className="text-[11px] text-slate-500">
                    {t('auth.passwordRule')}
                  </span>
                )}
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

              <button
                type="submit"
                disabled={busy}
                className="mt-1 flex items-center justify-center gap-2 rounded-md bg-emerald-500/90 px-3 py-2.5 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? (
                  <Loader2 size={15} className="animate-spin" aria-hidden />
                ) : mode === 'signin' ? (
                  <LogIn size={15} aria-hidden />
                ) : (
                  <UserPlus size={15} aria-hidden />
                )}
                {mode === 'signin' ? t('auth.signIn') : t('auth.createAccount')}
              </button>
            </form>

            {/* No sign-in secret is configured, so a restart ends every
                session. That is the owner's deliberate choice (2026-09-23), so
                this says what it means for the visitor — you may have to sign
                in again — rather than warning them about a server setting they
                cannot act on. */}
            {config?.persistentSessions === false && (
              <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
                {t('auth.sessionsMayEnd')}
              </p>
            )}
            <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
              {t('auth.noEmailsNote')}
            </p>
          </>
        )}
      </section>

      <p className="px-1 text-[11px] leading-relaxed text-slate-500">
        {t('auth.privacyNote')}{' '}
        <Link to="/legal" className="text-slate-400 underline hover:text-slate-200">
          {t('auth.privacyLink')}
        </Link>
      </p>
    </div>
  )
}
