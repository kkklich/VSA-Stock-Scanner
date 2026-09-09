// Component test for the Columns dropdown — the two things it does: show/hide
// a column, and move one left or right in the table. The state lives on the
// page (a localStorage-backed hook), so the test drives a tiny harness that
// holds it the same way.

import { describe, it, expect } from 'vitest'
import { useState } from 'react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, within } from '../test/utils'
import { ColumnPicker } from './ColumnPicker'
import {
  moveColumn,
  normalizeOrder,
  toggleColumnVisibility,
  visibleColumns,
  type ColumnOrder,
  type ColumnVisibility,
} from '../lib/rankingColumns'

function Harness() {
  const [value, setValue] = useState<ColumnVisibility>({})
  const [order, setOrder] = useState<ColumnOrder>(normalizeOrder([]))
  return (
    <>
      <ColumnPicker
        value={value}
        order={order}
        onToggle={(id) => setValue((v) => toggleColumnVisibility(v, id))}
        onMove={(id, delta) => setOrder((o) => moveColumn(o, id, delta, value))}
        onReset={() => {
          setValue({})
          setOrder(normalizeOrder([]))
        }}
        customized={false}
        visibleCount={visibleColumns(value, order).length}
      />
      {/* Mirrors what the table would render, so the test can assert the
          order the page actually gets — not just the menu's own list. */}
      <p data-testid="visible">
        {visibleColumns(value, order)
          .map((c) => c.id)
          .join(',')}
      </p>
    </>
  )
}

/** Open the dropdown and return its row list. */
async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /Columns/i }))
  return screen.getByText('Show columns').closest('div')?.parentElement as HTMLElement
}

describe('ColumnPicker', () => {
  it('toggles a column off and reports it to the page', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Harness />)
    await openPanel(user)

    expect(screen.getByTestId('visible').textContent).toContain('signal')
    await user.click(screen.getByRole('checkbox', { name: /^Signal$/i }))
    expect(screen.getByTestId('visible').textContent).not.toContain('signal')
  })

  it('moves a column one place with the arrows', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Harness />)
    await openPanel(user)

    // Default order puts the price columns before the rating.
    expect(screen.getByTestId('visible').textContent).toBe(
      'company,lastPrice,priceChangePct,rating,signal,daysSinceSignal',
    )

    // "VSA rating" is the picker's menu label for the rating column.
    await user.click(
      screen.getByRole('button', { name: /Move the VSA rating column left/i }),
    )
    expect(screen.getByTestId('visible').textContent).toBe(
      'company,lastPrice,rating,priceChangePct,signal,daysSinceSignal',
    )

    await user.click(
      screen.getByRole('button', { name: /Move the VSA rating column right/i }),
    )
    expect(screen.getByTestId('visible').textContent).toBe(
      'company,lastPrice,priceChangePct,rating,signal,daysSinceSignal',
    )
  })

  it('locks the identity column: it cannot be hidden or moved', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Harness />)
    const panel = await openPanel(user)

    const companyRow = within(panel)
      .getByRole('checkbox', { name: 'Company' })
      .closest('label')?.parentElement as HTMLElement
    expect(within(companyRow).getByRole('checkbox')).toBeDisabled()
    // No arrows at all on the pinned row — it has the "always on" tag instead.
    expect(within(companyRow).queryByRole('button')).not.toBeInTheDocument()
    expect(within(companyRow).getByText(/always on/i)).toBeInTheDocument()

    // Nothing can be moved above it either: the first movable row's "left"
    // arrow is disabled.
    expect(
      screen.getByRole('button', { name: /Move the Name column left/i }),
    ).toBeDisabled()
  })
})
