// The generic Education article page: the article follows the interface
// language, links to other articles stay inside the app, and an unknown
// address falls back to the Education landing page.

import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { EducationArticlePage } from './EducationArticlePage'
import i18n from '../i18n'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/education" element={<p>Education landing</p>} />
        <Route path="/education/:slug" element={<EducationArticlePage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('EducationArticlePage', () => {
  it('shows the English article with its table of contents', async () => {
    await i18n.changeLanguage('en')
    renderAt('/education/weinstein')

    expect(screen.getByRole('heading', { level: 1, name: 'Weinstein Stage 2' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: 'The six conditions StockPilot checks' }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'How well it has worked' })[0]).toHaveAttribute(
      'href',
      '#how-well-it-has-worked',
    )
    expect(screen.getByRole('link', { name: 'Education' })).toHaveAttribute('href', '/education')
  })

  it('shows the Polish article when the interface is Polish', async () => {
    await i18n.changeLanguage('pl')
    renderAt('/education/weinstein')

    expect(screen.getByRole('heading', { level: 1, name: 'Weinstein — Faza 2' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: 'Sześć warunków, które sprawdza StockPilot' }),
    ).toBeInTheDocument()
  })

  it('keeps links to other articles inside the app', async () => {
    await i18n.changeLanguage('en')
    renderAt('/education/vsa-rating')

    const link = screen.getByRole('link', { name: 'VSA Kompendium' })
    expect(link).toHaveAttribute('href', '/education/vsa-kompendium')
    expect(link).not.toHaveAttribute('target')
  })

  it('sends an unknown article back to the Education page', () => {
    renderAt('/education/no-such-article')
    expect(screen.getByText('Education landing')).toBeInTheDocument()
  })
})
