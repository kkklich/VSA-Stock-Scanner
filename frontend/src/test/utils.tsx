// Test helpers: a custom render that wraps the component under test in the app's
// providers (router + i18n) so hooks like useNavigate / useTranslation work.

import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../i18n'

function AllProviders({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{children}</MemoryRouter>
    </I18nextProvider>
  )
}

/** render() with the app's router + i18n providers already applied. */
export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  return render(ui, { wrapper: AllProviders, ...options })
}

// Re-export the rest of Testing Library so tests import from one place.
export * from '@testing-library/react'
