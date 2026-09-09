// Component tests for the two ranking layouts. The point being protected here
// is that BOTH render from one column list: a column the user hides in the
// picker has to vanish from the phone card list as well as the wide table,
// which is what makes the column choice mean anything on a phone.

import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, within } from '../test/utils'
import { RankingCardList, RankingTable, type RankingRow } from './RankingTable'
import { toRenderColumns, visibleColumns } from '../lib/rankingColumns'
import i18n from '../i18n'

function makeRow(over: Partial<RankingRow> = {}): RankingRow {
  return {
    ticker: 'KGH',
    name: 'KGHM Polska Miedz',
    lastPrice: 123.45,
    priceChangePct: 1.2,
    currentRating: 72,
    ratingChange: 3,
    lastSignal: 'Buy',
    daysSinceSignal: 2,
    sparkline: [1, 2, 3, 4, 5],
    volume: 100000,
    sector: 'Mining',
    aiConfidence: 60,
    distFrom52wHighPct: -5,
    distFrom52wLowPct: 20,
    isNew52wHigh: false,
    isNew52wLow: false,
    methodResults: {},
    combinedScore: 72,
    weeklyRating: null,
    weeklySignal: null,
    weeklyAgreement: null,
    ...over,
  }
}

/** Translated render columns for a given stored visibility map. */
function columnsFor(stored = {}) {
  return toRenderColumns(visibleColumns(stored), i18n.t.bind(i18n))
}

describe('RankingTable', () => {
  it('renders one header per column and one cell per row', () => {
    const columns = columnsFor()
    renderWithProviders(
      <RankingTable
        columns={columns}
        rows={[makeRow(), makeRow({ ticker: 'PKN', name: 'Orlen' })]}
        onOpen={() => {}}
        sortBy="currentRating"
        sortDir="desc"
        onSort={() => {}}
        minWidth={900}
      />,
    )
    expect(screen.getAllByRole('columnheader')).toHaveLength(columns.length)
    expect(screen.getAllByRole('row')).toHaveLength(3) // header + 2 rows
    expect(screen.getByText('KGH')).toBeInTheDocument()
    expect(screen.getByText('Orlen')).toBeInTheDocument()
  })

  it('drops a hidden column from the table', () => {
    renderWithProviders(
      <RankingTable
        columns={columnsFor({ signal: false })}
        rows={[makeRow()]}
        onOpen={() => {}}
        sortBy="currentRating"
        sortDir="desc"
        onSort={() => {}}
        minWidth={900}
      />,
    )
    expect(screen.queryByText('Buy')).not.toBeInTheDocument()
  })

  it('shows a column the user switched on', () => {
    renderWithProviders(
      <RankingTable
        columns={columnsFor({ sector: true })}
        rows={[makeRow()]}
        onOpen={() => {}}
        sortBy="currentRating"
        sortDir="desc"
        onSort={() => {}}
        minWidth={900}
      />,
    )
    expect(screen.getByText('Mining')).toBeInTheDocument()
  })

  it('sorts through the header of whichever column is shown', async () => {
    const user = userEvent.setup()
    const onSort = vi.fn()
    renderWithProviders(
      <RankingTable
        columns={columnsFor({ volume: true })}
        rows={[makeRow()]}
        onOpen={() => {}}
        sortBy="currentRating"
        sortDir="desc"
        onSort={onSort}
        minWidth={900}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Sort by Volume/i }))
    expect(onSort).toHaveBeenCalledWith('volume')
  })

  it('opens the row on click', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    renderWithProviders(
      <RankingTable
        columns={columnsFor()}
        rows={[makeRow()]}
        onOpen={onOpen}
        sortBy="currentRating"
        sortDir="desc"
        onSort={() => {}}
        minWidth={900}
      />,
    )
    await user.click(screen.getAllByRole('row')[1])
    expect(onOpen).toHaveBeenCalledWith('KGH')
  })
})

describe('RankingCardList (phone / tablet)', () => {
  it('renders one card per row, with the identity and price in the head', () => {
    renderWithProviders(
      <RankingCardList
        columns={columnsFor()}
        rows={[makeRow(), makeRow({ ticker: 'PKN', name: 'Orlen' })]}
        onOpen={() => {}}
      />,
    )
    const cards = screen.getAllByRole('button')
    expect(cards).toHaveLength(2)
    expect(within(cards[0]).getByText('KGH')).toBeInTheDocument()
    expect(within(cards[0]).getByText('KGHM Polska Miedz')).toBeInTheDocument()
    expect(within(cards[0]).getByText('+1.20%')).toBeInTheDocument()
  })

  // The reason this component exists: the picker has to reach the phone too.
  it('shows a switched-on column as a labelled chip', () => {
    renderWithProviders(
      <RankingCardList
        columns={columnsFor({ sector: true })}
        rows={[makeRow()]}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Sector')).toBeInTheDocument()
    expect(screen.getByText('Mining')).toBeInTheDocument()
  })

  it('drops a hidden column from the card as well as the table', () => {
    renderWithProviders(
      <RankingCardList
        columns={columnsFor({ sector: false, signal: false })}
        rows={[makeRow()]}
        onOpen={() => {}}
      />,
    )
    expect(screen.queryByText('Mining')).not.toBeInTheDocument()
    expect(screen.queryByText('Buy')).not.toBeInTheDocument()
  })

  it('uses the short chip label where one is defined', () => {
    renderWithProviders(
      <RankingCardList columns={columnsFor()} rows={[makeRow()]} onOpen={() => {}} />,
    )
    // The table header says "Rating (0–100)"; a card chip just says "Rating".
    expect(screen.getByText('Rating')).toBeInTheDocument()
    expect(screen.queryByText('Rating (0–100)')).not.toBeInTheDocument()
  })

  it('toggles a favorite without opening the row', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    const onToggleStar = vi.fn()
    renderWithProviders(
      <RankingCardList
        columns={columnsFor()}
        rows={[makeRow()]}
        onOpen={onOpen}
        onToggleStar={onToggleStar}
      />,
    )
    await user.click(screen.getByRole('button', { name: /favorite/i }))
    expect(onToggleStar).toHaveBeenCalledWith('KGH')
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('numbers the cards when the page asks for ranks', () => {
    renderWithProviders(
      <RankingCardList
        columns={columnsFor()}
        rows={[makeRow(), makeRow({ ticker: 'PKN' })]}
        onOpen={() => {}}
        showRank
        rankOffset={51}
      />,
    )
    expect(screen.getByText('51')).toBeInTheDocument()
    expect(screen.getByText('52')).toBeInTheDocument()
  })
})
