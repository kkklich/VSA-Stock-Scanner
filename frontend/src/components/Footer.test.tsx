// The footer is what makes the disclaimer and the publisher's contact details
// reachable from every page, so both must actually be in it.

import { describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import { Footer } from './Footer'

describe('Footer', () => {
  it('carries the short disclaimer, the legal link and the contact', () => {
    renderWithProviders(<Footer />)

    expect(screen.getByText(/neither investment advice nor a personal recommendation/i))
      .toBeInTheDocument()

    expect(
      screen.getByRole('link', {
        name: 'Legal information, terms of service and privacy policy',
      }),
    ).toHaveAttribute('href', '/legal')

    expect(screen.getByRole('link', { name: 'kklich97@gmail.com' })).toHaveAttribute(
      'href',
      'mailto:kklich97@gmail.com',
    )
  })
})
