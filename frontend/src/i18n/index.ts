// i18n bootstrap (react-i18next). Two languages — English and Polish — with the
// user's choice detected from localStorage first, then the browser, and
// persisted back to localStorage. English is the fallback for any missing key.
//
// Importing this module once (from main.tsx, and from the test setup) initialises
// the shared i18next instance. Resources are bundled inline so the first render
// is synchronous — no Suspense/loading state is needed for language files.

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import pl from './locales/pl.json'

/** Supported UI languages, in menu order. */
export const SUPPORTED_LANGUAGES = ['en', 'pl'] as const
export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number]

/** localStorage key under which the detector persists the chosen language. */
export const LANGUAGE_STORAGE_KEY = 'stockpilot.lang'

export const resources = {
  en: { translation: en },
  pl: { translation: pl },
} as const

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGUAGES as unknown as string[],
    // Treat "pl-PL" etc. as "pl" so a Polish browser is detected correctly.
    load: 'languageOnly',
    nonExplicitSupportedLngs: true,
    interpolation: {
      // React already escapes rendered values, so i18next must not double-escape.
      escapeValue: false,
    },
    react: {
      // Resources are bundled inline and init is synchronous, so there is
      // nothing to wait for — skip Suspense and avoid needing a boundary.
      useSuspense: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      caches: ['localStorage'],
    },
  })

export default i18n
