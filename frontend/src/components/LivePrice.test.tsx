// The live-price marks: the note above a list, the dot beside a price and the
// chip on the stock page. Each must say plainly that the price is today's so
// far while the rating is the last finished session's.

import { describe, expect, it } from 'vitest'
import type { ApiLivePrice } from '../api/stocksApi'
import { renderWithProviders, screen } from '../test/utils'
import { LiveChip, LiveDot, LiveNote } from './LivePrice'

function live(overrides: Partial<ApiLivePrice> = {}): ApiLivePrice {
  const at = new Date()
  at.setHours(13, 44, 0, 0)
  return {
    sessionDate: '2026-09-25',
    price: 110,
    open: 101,
    high: 111,
    low: 100,
    volume: 90_000,
    previousClose: 100,
    changePct: 10,
    asOf: at.toISOString(),
    fetchedAt: at.toISOString(),
    ...overrides,
  }
}

describe('LiveNote', () => {
  it('says nothing outside trading hours', () => {
    const { container } = renderWithProviders(
      <LiveNote rows={[{ market: 'gpw', lastSession: '2026-09-24', live: null }]} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('names the time and the finished session for one market', () => {
    renderWithProviders(
      <LiveNote rows={[{ market: 'gpw', lastSession: '2026-09-24', live: live() }]} />,
    )
    const note = screen.getByText(/today's session so far, as of 13:44/)
    expect(note).toHaveTextContent('last finished session (24.09)')
  })

  it('lists each live market with its own time', () => {
    const later = new Date()
    later.setHours(17, 30, 0, 0)
    renderWithProviders(
      <LiveNote
        rows={[
          { market: 'gpw', lastSession: '2026-09-24', live: live() },
          {
            market: 'us',
            lastSession: '2026-09-24',
            live: live({ asOf: later.toISOString() }),
          },
        ]}
      />,
    )
    expect(screen.getByText(/GPW \(Poland\) 13:44 · USA 17:30/)).toBeInTheDocument()
  })
})

describe('LiveDot', () => {
  it('explains itself in its tooltip', () => {
    renderWithProviders(<LiveDot live={live()} />)
    const dot = screen.getByRole('img')
    expect(dot).toHaveAttribute('title', expect.stringContaining('as of 13:44'))
    expect(dot.className).toContain('bg-sky-400')
  })

  it('is hollow for a stock that has not traded yet today', () => {
    renderWithProviders(<LiveDot live={live({ volume: 0 })} />)
    const dot = screen.getByRole('img')
    expect(dot).toHaveAttribute('title', expect.stringContaining('No trade yet today'))
    expect(dot.className).toContain('ring-sky-400')
    expect(dot.className).not.toContain('bg-sky-400')
  })
})

describe('LiveChip', () => {
  it('shows the time of the price', () => {
    renderWithProviders(<LiveChip live={live()} />)
    expect(screen.getByText('Today 13:44')).toBeInTheDocument()
  })

  it('says when there was no trade yet', () => {
    renderWithProviders(<LiveChip live={live({ volume: 0 })} />)
    expect(screen.getByText('No trade today yet')).toBeInTheDocument()
  })
})
