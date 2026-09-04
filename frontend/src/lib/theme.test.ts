// Theme switching: the stored preference, what it resolves to, and what ends
// up on <html>. The rest of the app reads its colours from CSS variables that
// hang off the `dark` class, so these three things are the whole contract.

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_THEME,
  getResolvedTheme,
  getThemePreference,
  initTheme,
  readStoredTheme,
  resolveTheme,
  setThemePreference,
  THEME_STORAGE_KEY,
} from './theme'

/** Pretend the OS is set to light (or dark); jsdom has no matchMedia. */
function mockSystem(prefersLight: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: prefersLight,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  setThemePreference(DEFAULT_THEME, { persist: false })
})

describe('theme', () => {
  it('defaults to dark when nothing is stored', () => {
    expect(DEFAULT_THEME).toBe('dark')
    expect(readStoredTheme()).toBe('dark')
  })

  it('ignores a stored value that is not a theme', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'chartreuse')
    expect(readStoredTheme()).toBe('dark')
  })

  it('reads back a stored choice', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    expect(readStoredTheme()).toBe('light')
  })

  it('resolves "system" to what the OS asks for', () => {
    mockSystem(true)
    expect(resolveTheme('system')).toBe('light')
    mockSystem(false)
    expect(resolveTheme('system')).toBe('dark')
  })

  it('resolves an explicit choice without consulting the OS', () => {
    mockSystem(true)
    expect(resolveTheme('dark')).toBe('dark')
    expect(resolveTheme('light')).toBe('light')
  })

  it('puts the `dark` class on <html> for the dark theme only', () => {
    setThemePreference('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(document.documentElement.dataset.theme).toBe('light')

    setThemePreference('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('remembers the choice, and can be told not to', () => {
    setThemePreference('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')

    localStorage.clear()
    setThemePreference('dark', { persist: false })
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
    expect(getThemePreference()).toBe('dark')
  })

  it('keeps the preference and the resolved theme apart under "system"', () => {
    mockSystem(true)
    setThemePreference('system')
    expect(getThemePreference()).toBe('system')
    expect(getResolvedTheme()).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('follows the OS while "system" is selected, and only then', () => {
    // A media query whose `change` handler the test can fire by hand.
    let handler: (() => void) | undefined
    let prefersLight = false
    const media = {
      get matches() {
        return prefersLight
      },
      addEventListener: (_: string, fn: () => void) => {
        handler = fn
      },
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue(media))

    localStorage.setItem(THEME_STORAGE_KEY, 'system')
    initTheme()
    expect(getResolvedTheme()).toBe('dark')

    // The OS flips to light while the app is open.
    prefersLight = true
    handler?.()
    expect(getResolvedTheme()).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)

    // With an explicit choice, the OS is ignored.
    setThemePreference('dark')
    prefersLight = true
    handler?.()
    expect(getResolvedTheme()).toBe('dark')
  })

  it('survives localStorage being unavailable', () => {
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('denied')
      })
    const setItem = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new Error('denied')
      })

    expect(readStoredTheme()).toBe(DEFAULT_THEME)
    expect(() => setThemePreference('light')).not.toThrow()
    expect(getResolvedTheme()).toBe('light')

    getItem.mockRestore()
    setItem.mockRestore()
  })
})
