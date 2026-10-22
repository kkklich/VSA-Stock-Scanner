import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import i18n from '../i18n'
import { LongTermFactorBar } from './LongTermFactorBar'

afterEach(async () => { await i18n.changeLanguage('en') })

describe('LongTermFactorBar', () => {
  it('exposes the factor name, exact range and readable localized value', () => {
    renderWithProviders(<LongTermFactorBar label="Quality" value={72.35} />)
    const meter = screen.getByRole('meter', { name: 'Quality' })
    expect(meter).toHaveAttribute('aria-valuemin', '0')
    expect(meter).toHaveAttribute('aria-valuemax', '100')
    expect(meter).toHaveAttribute('aria-valuenow', '72.35')
    expect(meter).toHaveAttribute('aria-valuetext', '72.4 / 100')
    expect(screen.getByText('72.4')).toBeVisible()
  })

  it('uses the selected language for the visible and accessible decimal separator', async () => {
    await i18n.changeLanguage('pl')
    renderWithProviders(<LongTermFactorBar label="Jakość" value={45.5} />)
    expect(screen.getByText('45,5')).toBeVisible()
    expect(screen.getByRole('meter', { name: 'Jakość' })).toHaveAttribute('aria-valuetext', '45,5 / 100')
  })

  it.each([null, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    'keeps unavailable value %s distinct from a score of zero', (value) => {
      renderWithProviders(<LongTermFactorBar label="Value" value={value} />)
      expect(screen.getByText('—')).toBeVisible()
      expect(screen.getByRole('img', { name: 'Value: No complete score' })).toBeInTheDocument()
      expect(screen.queryByRole('meter')).not.toBeInTheDocument()
      expect(screen.queryByText('0')).not.toBeInTheDocument()
    },
  )

  it.each([[-5, 0], [0, 0], [100, 100], [160, 100]])(
    'keeps input %s within the fixed scale, showing %s', (value, expected) => {
      renderWithProviders(<LongTermFactorBar label="Momentum" value={value} />)
      const meter = screen.getByRole('meter', { name: 'Momentum' })
      expect(meter).toHaveAttribute('aria-valuenow', String(expected))
      expect(screen.getByText(String(expected))).toBeVisible()
      expect(meter.lastElementChild?.firstElementChild).toHaveStyle({ width: `${expected}%` })
    },
  )
})
