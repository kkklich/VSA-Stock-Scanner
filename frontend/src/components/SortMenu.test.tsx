// The card-list sort control (phones/tablets). It is the touch equivalent of
// the desktop table headers, including their shift-click: the active sort
// levels sit at the top of the panel with their own direction switches and a
// remove button, and the columns below them append a "then by" level.

import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../test/utils'
import { SortMenu, type SortOption } from './SortMenu'
import type { SortLevel } from '../lib/sorting'

type Key = 'combinedScore' | 'lastPrice' | 'ticker'

const options: SortOption<Key>[] = [
  { key: 'combinedScore', label: 'Combined' },
  { key: 'lastPrice', label: 'Price' },
  { key: 'ticker', label: 'Symbol' },
]

const ONE_LEVEL: SortLevel<Key>[] = [{ key: 'combinedScore', dir: 'desc' }]

function setup(
  overrides: Partial<Parameters<typeof SortMenu<Key>>[0]> = {},
) {
  const onSort = vi.fn()
  const onSortDirChange = vi.fn()
  const onRemoveLevel = vi.fn()
  renderWithProviders(
    <SortMenu
      options={options}
      sort={ONE_LEVEL}
      onSort={onSort}
      onSortDirChange={onSortDirChange}
      onRemoveLevel={onRemoveLevel}
      {...overrides}
    />,
  )
  return { onSort, onSortDirChange, onRemoveLevel }
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
    // An unsorted column is offered as a "then by" level, not as a radio.
    expect(screen.getByRole('menuitem', { name: /Price/ })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Combined descending' }),
    ).toHaveAttribute('aria-pressed', 'true')
  })

  it('replaces the sort when an active level is tapped', async () => {
    const user = userEvent.setup()
    const { onSort } = setup()

    await user.click(screen.getByRole('button', { name: /Combined/ }))
    await user.click(screen.getByRole('menuitemradio', { name: /Combined/ }))

    // `false` = not additive: back to a plain single-column sort.
    expect(onSort).toHaveBeenCalledWith('combinedScore', false)
  })

  it('adds a "then by" level when an unsorted column is tapped', async () => {
    const user = userEvent.setup()
    const { onSort } = setup()

    await user.click(screen.getByRole('button', { name: /Combined/ }))
    await user.click(screen.getByRole('menuitem', { name: /Price/ }))

    // `true` = additive: Price becomes the tie-break, Combined stays primary.
    expect(onSort).toHaveBeenCalledWith('lastPrice', true)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('sets one level’s direction explicitly', async () => {
    const user = userEvent.setup()
    const { onSortDirChange } = setup()

    await user.click(screen.getByRole('button', { name: /Combined/ }))
    await user.click(screen.getByRole('button', { name: 'Combined ascending' }))

    expect(onSortDirChange).toHaveBeenCalledWith('combinedScore', 'asc')
  })

  describe('with several levels', () => {
    const TWO_LEVELS: SortLevel<Key>[] = [
      { key: 'combinedScore', dir: 'desc' },
      { key: 'ticker', dir: 'asc' },
    ]

    it('counts the extra levels on the trigger and numbers them in the panel', async () => {
      const user = userEvent.setup()
      setup({ sort: TWO_LEVELS })

      // The button names the primary column and says there is one more level.
      const trigger = screen.getByRole('button', { name: /Combined/ })
      expect(trigger).toHaveTextContent('+1')

      await user.click(trigger)
      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('2')).toBeInTheDocument()
      // Both are listed as levels; only the untouched column is addable.
      expect(screen.getByRole('menuitemradio', { name: /Symbol/ })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /Price/ })).toBeInTheDocument()
    })

    it('removes a level', async () => {
      const user = userEvent.setup()
      const { onRemoveLevel } = setup({ sort: TWO_LEVELS })

      await user.click(screen.getByRole('button', { name: /Combined/ }))
      await user.click(
        screen.getByRole('button', { name: 'Remove Symbol from the sort' }),
      )

      expect(onRemoveLevel).toHaveBeenCalledWith('ticker')
    })

    it('will not remove the last remaining level', async () => {
      const user = userEvent.setup()
      const { onRemoveLevel } = setup()

      await user.click(screen.getByRole('button', { name: /Combined/ }))
      const remove = screen.getByRole('button', {
        name: 'Remove Combined from the sort',
      })
      expect(remove).toBeDisabled()
      await user.click(remove)
      expect(onRemoveLevel).not.toHaveBeenCalled()
    })
  })
})
