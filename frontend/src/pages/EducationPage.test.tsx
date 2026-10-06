import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, within } from '../test/utils'
import { EducationPage } from './EducationPage'
import i18n from '../i18n'

const useMethodsMock = vi.hoisted(() => vi.fn())

vi.mock('../hooks/useMethods', () => ({ useMethods: useMethodsMock }))

const METHODS = [
  {
    id: 'vsa4',
    name: 'VSA V4',
    description: 'The owner-supplied VSA program.',
    source: 'Rafal Glinicki',
    sourceUrl: 'https://example.com/course',
    direction: 'Bullish',
  },
  {
    id: 'minervini',
    name: 'Minervini Trend Template',
    description: 'Trend structure.',
    source: 'Mark Minervini',
    sourceUrl: null,
    direction: 'Bullish',
  },
  {
    id: 'future_method',
    name: 'A Future Method',
    description: 'Not written up yet.',
    source: 'Someone',
    sourceUrl: null,
    direction: 'Bullish',
  },
]

afterEach(async () => {
  useMethodsMock.mockReset()
  await i18n.changeLanguage('en')
})

describe('EducationPage', () => {
  it('lists the articles and one card per trading method', () => {
    useMethodsMock.mockReturnValue({ methods: METHODS, loading: false, error: null })
    renderWithProviders(<EducationPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Education' })).toBeInTheDocument()

    const articles = screen.getByRole('region', { name: 'Articles' })
    const articleLinks = within(articles)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
    expect(articleLinks).toEqual([
      '/education/vsa-rating',
      '/education/minervini',
      '/education/volume-breakout',
      '/education/weinstein',
      '/education/pocket-pivot',
      '/education/vsa-kompendium',
    ])

    const methods = screen.getByRole('region', { name: 'Trading methods in StockPilot' })
    const cards = within(methods).getAllByRole('listitem')
    expect(cards).toHaveLength(3)

    // A method the Kompendium explains links it...
    expect(within(cards[0]).getByRole('link', { name: /VSA Kompendium/ })).toHaveAttribute(
      'href',
      '/education/vsa-kompendium',
    )
    expect(within(cards[0]).getByRole('link', { name: /Rafal Glinicki/ })).toHaveAttribute(
      'href',
      'https://example.com/course',
    )
    expect(within(cards[1]).getByRole('link', { name: /Minervini Trend Template/ })).toHaveAttribute(
      'href',
      '/education/minervini',
    )
    expect(within(cards[1]).getByText('Mark Minervini')).toBeInTheDocument()
    // ...and one without an article yet says so.
    expect(within(cards[2]).getByText('Article coming soon')).toBeInTheDocument()
  })

  it('keeps the articles when the method list cannot be loaded', () => {
    useMethodsMock.mockReturnValue({ methods: [], loading: false, error: 'boom' })
    renderWithProviders(<EducationPage />)

    expect(screen.getByText(/could not be loaded/)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /VSA Kompendium/ }).length).toBeGreaterThan(0)
  })

  it('is translated to Polish', async () => {
    useMethodsMock.mockReturnValue({ methods: METHODS, loading: false, error: null })
    await i18n.changeLanguage('pl')
    renderWithProviders(<EducationPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Edukacja' })).toBeInTheDocument()
    // A method's card description is Polish too, not the backend's English…
    expect(screen.getByText(/^Mechaniczny filtr Marka Minerviniego/)).toBeInTheDocument()
    expect(screen.queryByText('Trend structure.')).toBeNull()
    // …and a method nobody has translated yet still shows its English text.
    expect(screen.getByText('Not written up yet.')).toBeInTheDocument()
    expect(screen.getByText('Artykuł wkrótce')).toBeInTheDocument()
  })
})
