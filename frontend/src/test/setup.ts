// Global test setup, loaded once before the suite (see vitest.config.ts).
// - Registers @testing-library/jest-dom's DOM matchers on Vitest's `expect`.
// - Initialises i18n and pins the language to English so assertions can match
//   the English copy regardless of the CI machine's locale.
// - Unmounts React trees after each test (RTL's auto-cleanup only runs when
//   Vitest globals are enabled, which they are not here).
// - Stubs ResizeObserver, which jsdom does not implement.

import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import i18n from '../i18n'

void i18n.changeLanguage('en')

// jsdom ships no ResizeObserver, but every browser the app targets has had one
// for years, and StockChart uses it to keep the canvas sized to its container.
// A no-op stand-in is enough: nothing in jsdom lays anything out, so the
// callback would never have anything to report anyway.
if (!('ResizeObserver' in globalThis)) {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof globalThis.ResizeObserver
}

afterEach(() => {
  cleanup()
})
