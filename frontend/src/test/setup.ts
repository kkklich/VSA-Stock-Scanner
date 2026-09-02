// Global test setup, loaded once before the suite (see vitest.config.ts).
// - Registers @testing-library/jest-dom's DOM matchers on Vitest's `expect`.
// - Initialises i18n and pins the language to English so assertions can match
//   the English copy regardless of the CI machine's locale.
// - Unmounts React trees after each test (RTL's auto-cleanup only runs when
//   Vitest globals are enabled, which they are not here).

import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import i18n from '../i18n'

void i18n.changeLanguage('en')

afterEach(() => {
  cleanup()
})
