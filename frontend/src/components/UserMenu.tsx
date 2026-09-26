// The sign-in control in the top bar.
//
// Signed out it is a "Sign in" button; signed in it is the visitor's initials
// with a small menu (their name and address, a link to Settings, Sign out).
// It replaces the decorative "AM" avatar the top bar used to show, which
// looked like an account and was not one.
//
// Hidden entirely when the deployment cannot store accounts (no database):
// offering a form that can only answer "unavailable" is worse than not
// offering it.

import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LogIn, LogOut, Settings as SettingsIcon } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { initialsOf } from '../lib/format'

export function UserMenu() {
  const { t } = useTranslation()
  const { user, loading, config, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // Close on a click outside or Escape — a menu that stays open while the user
  // works elsewhere reads as a stuck UI.
  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  // Accounts need a database; without one there is nothing to sign in to.
  if (config && !config.enabled) return null
  // Don't flash "Sign in" at someone who is about to be recognised.
  if (loading) return <div className="h-8 w-8 shrink-0" aria-hidden />

  if (!user) {
    if (pathname === '/login') return null
    return (
      <Link
        to="/login"
        state={{ from: pathname }}
        className="flex shrink-0 items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800/60 px-2.5 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-slate-800"
      >
        <LogIn size={14} aria-hidden />
        <span className="hidden sm:inline">{t('auth.signIn')}</span>
      </Link>
    )
  }

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('auth.accountMenu')}
        title={user.email}
        className="grid h-8 w-8 place-items-center rounded-full bg-emerald-500/15 text-[11px] font-semibold text-emerald-400 ring-1 ring-emerald-500/40 hover:bg-emerald-500/25"
      >
        {initialsOf(user.displayName, user.email)}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-10 z-50 w-56 rounded-lg border border-slate-800 bg-slate-900 p-1.5 shadow-xl"
        >
          <div className="px-2.5 py-2">
            <p className="truncate text-xs font-semibold text-slate-200">
              {user.displayName}
            </p>
            <p className="truncate text-[11px] text-slate-500">{user.email}</p>
          </div>
          <div className="my-1 border-t border-slate-800" />
          <Link
            to="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs text-slate-300 hover:bg-slate-800"
          >
            <SettingsIcon size={14} aria-hidden />
            {t('auth.accountSettings')}
          </Link>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              signOut()
              navigate('/')
            }}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-xs text-slate-300 hover:bg-slate-800"
          >
            <LogOut size={14} aria-hidden />
            {t('auth.signOut')}
          </button>
        </div>
      )}
    </div>
  )
}
