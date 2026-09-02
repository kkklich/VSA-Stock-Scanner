// Compact EN / PL language toggle for the top bar. Switching updates the shared
// i18next instance (which re-renders every translated component) and persists the
// choice to localStorage via the language detector.

import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES, type AppLanguage } from '../i18n'

const LABELS: Record<AppLanguage, string> = { en: 'EN', pl: 'PL' }

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()
  // i18n.language can be a region variant (e.g. "en-US"); match on the base tag.
  const active = (i18n.resolvedLanguage ?? i18n.language ?? 'en').split('-')[0]

  return (
    <div
      role="group"
      aria-label={t('language.label')}
      className="flex overflow-hidden rounded-md border border-slate-700"
    >
      {SUPPORTED_LANGUAGES.map((lng) => {
        const isActive = lng === active
        return (
          <button
            key={lng}
            type="button"
            onClick={() => i18n.changeLanguage(lng)}
            aria-pressed={isActive}
            title={t(`language.${lng}`)}
            className={
              'px-2 py-1 text-[11px] font-semibold transition-colors ' +
              (isActive
                ? 'bg-slate-700 text-slate-100'
                : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
            }
          >
            {LABELS[lng]}
          </button>
        )
      })}
    </div>
  )
}
