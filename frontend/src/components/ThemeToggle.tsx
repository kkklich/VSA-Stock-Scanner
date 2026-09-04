// Light / Dark / System theme switch for the top bar. The choice is stored in
// localStorage and applied to <html> (see src/lib/theme.ts); dark is the app's
// default.
//
// On a phone the top bar has no room for a three-button group next to the
// language switch (it would squeeze the page title out), so below `sm` this
// collapses to a single button showing the current setting, which cycles
// Light → Dark → System. The full group — matching the LanguageSwitcher beside
// it — returns at `sm` and up. The Settings page has the same choice as a
// labelled row, for anyone who prefers reading the options.

import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { THEME_PREFERENCES, useTheme, type ThemePreference } from '../lib/theme'

const ICONS: Record<ThemePreference, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
}

export function ThemeToggle() {
  const { preference, setPreference } = useTheme()
  const { t } = useTranslation()

  const CurrentIcon = ICONS[preference]
  const next =
    THEME_PREFERENCES[
      (THEME_PREFERENCES.indexOf(preference) + 1) % THEME_PREFERENCES.length
    ]

  return (
    <>
      {/* Phones: one button, cycling through the three settings. */}
      <button
        type="button"
        onClick={() => setPreference(next)}
        title={t('theme.cycle', { next: t(`theme.${next}`) })}
        aria-label={t('theme.cycle', { next: t(`theme.${next}`) })}
        className="rounded-md border border-slate-700 bg-slate-900 px-1.5 py-1 text-slate-300 hover:bg-slate-800 hover:text-slate-100 sm:hidden"
      >
        <CurrentIcon size={14} />
      </button>

      {/* Tablet and up: the full three-way group. */}
      <div
        role="group"
        aria-label={t('theme.label')}
        className="hidden overflow-hidden rounded-md border border-slate-700 sm:flex"
      >
        {THEME_PREFERENCES.map((option) => {
          const Icon = ICONS[option]
          const isActive = option === preference
          return (
            <button
              key={option}
              type="button"
              onClick={() => setPreference(option)}
              aria-pressed={isActive}
              title={t(`theme.${option}`)}
              aria-label={t(`theme.${option}`)}
              className={
                'px-1.5 py-1 transition-colors ' +
                (isActive
                  ? 'bg-slate-700 text-slate-100'
                  : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
              }
            >
              <Icon size={14} />
            </button>
          )
        })}
      </div>
    </>
  )
}
