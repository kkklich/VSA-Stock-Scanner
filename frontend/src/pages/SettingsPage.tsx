// Settings. Only the Appearance section is real so far: the light / dark theme
// choice (the rest of the blueprint's settings — default date range, badge
// thresholds, alert preferences — are still to come, see agent/ROADMAP.md #7).

import { Construction, Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { THEME_PREFERENCES, useTheme, type ThemePreference } from '../lib/theme'

const ICONS: Record<ThemePreference, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
}

export function SettingsPage() {
  const { t } = useTranslation()
  const { preference, resolved, setPreference } = useTheme()

  return (
    <div className="flex max-w-3xl flex-col gap-6 p-4 sm:p-6">
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 sm:p-5">
        <h2 className="text-sm font-semibold text-slate-200">
          {t('theme.settingsTitle')}
        </h2>
        <p className="mt-1 max-w-xl text-xs leading-relaxed text-slate-500">
          {t('theme.settingsHint')}
        </p>

        <div
          role="radiogroup"
          aria-label={t('theme.label')}
          className="mt-4 grid gap-2 sm:grid-cols-3"
        >
          {THEME_PREFERENCES.map((option) => {
            const Icon = ICONS[option]
            const isActive = option === preference
            return (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={isActive}
                onClick={() => setPreference(option)}
                className={
                  'flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm transition-colors ' +
                  (isActive
                    ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
                    : 'border-slate-800 bg-slate-800/40 text-slate-300 hover:bg-slate-800')
                }
              >
                <Icon size={16} />
                <span className="font-medium">{t(`theme.${option}`)}</span>
              </button>
            )
          })}
        </div>

        <p className="mt-3 text-xs text-slate-500">
          {t('theme.active', { theme: t(`theme.${resolved}`).toLowerCase() })}
        </p>
      </section>

      <section className="flex items-start gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500">
        <Construction size={18} className="mt-0.5 shrink-0" />
        <p className="leading-relaxed">
          More settings (default date range, rating-badge thresholds, alert
          preferences) are part of the blueprint and will be added here.
        </p>
      </section>
    </div>
  )
}
