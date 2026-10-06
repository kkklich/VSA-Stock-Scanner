// The Kompendium is published in Polish and English (owner's decision,
// 2026-09-26): the article, its table of contents and its diagrams follow
// the interface language.

import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import { VsaKompendiumPage } from './VsaKompendiumPage'
import i18n from '../i18n'

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('VsaKompendiumPage', () => {
  it('shows the English article and diagrams in English', async () => {
    await i18n.changeLanguage('en')
    renderWithProviders(<VsaKompendiumPage />)

    expect(
      screen.getByRole('heading', { level: 2, name: '1. What VSA is' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '1. Czym jest VSA' })).toBeNull()
    expect(screen.getAllByRole('link', { name: '1. What VSA is' })[0]).toHaveAttribute(
      'href',
      '#1-what-vsa-is',
    )
    expect(screen.getByRole('img', { name: /A candle/ })).toHaveAttribute(
      'src',
      '/vsa/anatomia.en.svg',
    )
    expect(screen.getByRole('link', { name: /Download PDF \(Polish\)/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Education' })).toHaveAttribute('href', '/education')
  })

  it('shows the Polish article and diagrams in Polish', async () => {
    await i18n.changeLanguage('pl')
    renderWithProviders(<VsaKompendiumPage />)

    expect(
      screen.getByRole('heading', { level: 2, name: '1. Czym jest VSA' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Świeca/ })).toHaveAttribute(
      'src',
      '/vsa/anatomia.svg',
    )
  })
})
