// The legal page carries the three documents a public financial-information
// site has to publish, plus the publisher's contact data. These tests guard the
// things that would quietly break the compliance value of the page: a missing
// document, a missing contact, an untranslated section, or a placeholder
// address leaking onto the live site.

import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import { LegalPage } from './LegalPage'
import i18n from '../i18n'
import en from '../i18n/locales/en.json'
import pl from '../i18n/locales/pl.json'

/** Every leaf key path of a nested translation object, sorted. */
function keyPaths(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix]
  return Object.entries(value as Record<string, unknown>)
    .flatMap(([key, child]) => keyPaths(child, prefix ? `${prefix}.${key}` : key))
    .sort()
}

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('LegalPage', () => {
  it('shows all three legal documents', () => {
    renderWithProviders(<LegalPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Legal information' }),
    ).toBeInTheDocument()

    for (const title of ['Legal disclaimer', 'Terms of service', 'Privacy policy']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument()
    }

    // Spot-check one sub-section of each document.
    expect(screen.getByRole('heading', { name: 'Risk' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '4. Rules of use' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Retention' })).toBeInTheDocument()
  })

  it('publishes the contact details as a usable mailto link', () => {
    renderWithProviders(<LegalPage />)

    const mail = screen.getByRole('link', { name: 'kklich97@gmail.com' })
    expect(mail).toHaveAttribute('href', 'mailto:kklich97@gmail.com')
    expect(screen.getByText('Krzysztof Klich')).toBeInTheDocument()
  })

  it('hides the address row while no address is configured', () => {
    renderWithProviders(<LegalPage />)

    // `legal.publisher.address` is deliberately empty — the row must stay off
    // the page rather than render an empty or placeholder value.
    expect(en.legal.publisher.address).toBe('')
    expect(screen.queryByText('Address')).not.toBeInTheDocument()
  })

  it('renders translated copy, not raw keys, in Polish too', async () => {
    await i18n.changeLanguage('pl')
    const { container } = renderWithProviders(<LegalPage />)

    expect(
      screen.getByRole('heading', { level: 2, name: 'Polityka prywatności' }),
    ).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/legal\.[a-z]/i)
  })

  it('keeps the Polish and English legal copy in step', () => {
    expect(keyPaths(pl.legal)).toEqual(keyPaths(en.legal))
  })
})
