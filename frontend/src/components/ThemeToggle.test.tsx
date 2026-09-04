// The top-bar theme switch: pressing an option applies it and marks itself
// active, and the phone-sized single button cycles through the three settings.

import { afterEach, describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../test/utils'
import { ThemeToggle } from './ThemeToggle'
import { DEFAULT_THEME, getThemePreference, setThemePreference } from '../lib/theme'

afterEach(() => {
  localStorage.clear()
  setThemePreference(DEFAULT_THEME, { persist: false })
})

describe('ThemeToggle', () => {
  it('marks the active theme and switches when another is pressed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ThemeToggle />)

    // The three-way group (the wide-screen variant) carries aria-pressed.
    const dark = screen.getByRole('button', { name: 'Dark', pressed: true })
    expect(dark).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Light', pressed: false }))

    expect(getThemePreference()).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(screen.getByRole('button', { name: 'Light', pressed: true })).toBeInTheDocument()
  })

  it('cycles Light → Dark → System on the compact (phone) button', async () => {
    const user = userEvent.setup()
    setThemePreference('light', { persist: false })
    renderWithProviders(<ThemeToggle />)

    const compact = () => screen.getByRole('button', { name: /switch to/i })

    expect(compact()).toHaveAccessibleName('Theme — switch to Dark')
    await user.click(compact())
    expect(getThemePreference()).toBe('dark')

    await user.click(compact())
    expect(getThemePreference()).toBe('system')
  })
})
