// The card-list sort control (phones/tablets): picking a column, flipping the
// direction on the active one, and the explicit ascending/descending switch.

import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../test/utils'
import { SortMenu, type SortOption } from './SortMenu'

type Key = 'combinedScore' | 'lastPrice' | 'ticker'

const options: SortOption<Key>[] = [
  { key: 'combinedScore', label: 'Combined' },
  { key: 'lastPrice', label: 'Price' },
  { key: 'ticker', label: 'Symbol' },
]

function setup(overrides: Partial<Parameters<typeof SortMenu<Key>>[0]> = {}) {
  const onSort = vi.fn()
  const onSortDirChange = vi.fn()
  renderWithProviders(
    <SortMenu
      options={options}
      sortBy="combinedScore"
      sortDir="desc"
      onSort={onSort}
      onSortDirChange={onSortDirChange}
      {...overrides}
    />,
  )
  return { onSort, onSortDirChange }
}

describe('SortMenu', () => {
  it('shows the active column on the button and marks it in the menu', async () => {
    const user = userEvent.setup()
    setup()

    const trigger = screen.getByRole('button', { name: /Combined/ })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    await user.click(trigger)

    expect(
      screen.getByRole('menuitemradio', { name: /Combined/, checked: true }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('menuitemradio', { name: 'Price', checked: false }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Descending/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('sorts by the chosen column and closes', async () => {
    const user = userEvent.setup()
    const { onSort } = setup()

    await user.click(screen.getByRole('button', { name: /Combined/ }))
    await user.click(screen.getByRole('menuitemradio', { name: 'Price' }))

    expect(onSort).toHaveBeenCalledWith('lastPrice')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('keeps the menu open when the active column is tapped again (flip)', async () => {
    const user = userEvent.setup()
    const { onSort } = setup()

    await user.click(screen.getByRole('button', { name: /Combined/ }))
    await user.click(screen.getByRole('menuitemradio', { name: /Combined/ }))

    expect(onSort).toHaveBeenCalledWith('combinedScore')
    expect(screen.getByRole('menu')).toBeInTheDocument()
  })

  it('sets the direction explicitly', async () => {
    const user = userEvent.setup()
    const { onSortDirChange } = setup()

    await user.click(screen.getByRole('button', { name: /Combined/ }))
    await user.click(screen.getByRole('button', { name: /Ascending/ }))

    expect(onSortDirChange).toHaveBeenCalledWith('asc')
  })
})
