// Component test for the stock chart's method chooser and colour key. The chart
// answers two questions with two colours: WHICH method drew a marker (its dot,
// in the method's own colour — the chip shows the same colour) and whether it
// is GOOD OR BAD news (the label, green / red / grey). The legend is the only
// place that says so, so it must show both, in the chart's own values.

import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../test/utils'
import { ChartMethodLegend, type ChartMethodLegendItem } from './ChartMethodLegend'
import { CHART_THEME } from '../lib/chartTheme'

// The app's default theme, which is what the legend resolves to under jsdom.
const PALETTE = CHART_THEME.dark

const ITEMS: ChartMethodLegendItem[] = [
  { id: 'vsa', name: 'VSA rating', shape: 'arrow', color: PALETTE.bull, count: 7, selected: true },
  {
    id: 'minervini',
    name: 'Minervini Trend Template',
    shape: 'circle',
    color: PALETTE.methodColors.minervini,
    count: 3,
    selected: true,
  },
  {
    id: 'vsa4',
    name: 'VSA V4',
    shape: 'circle',
    color: PALETTE.methodColors.vsa4,
    count: 4,
    selected: false,
  },
]

/** How jsdom reports a `#rrggbb` colour once it is set as an inline style. */
function rgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}

describe('ChartMethodLegend', () => {
  it('writes each direction in the colour the chart labels use', () => {
    renderWithProviders(<ChartMethodLegend items={ITEMS} onToggle={() => {}} />)

    const cases = [
      ['Positive (strength)', PALETTE.bull],
      ['Negative (weakness)', PALETTE.bear],
      ['Watch (not taken)', PALETTE.neutral],
    ] as const
    for (const [label, color] of cases) {
      expect(screen.getByText(label).style.color).toBe(rgb(color))
    }
    expect(screen.getByText('Colours:')).toBeInTheDocument()
    // …and says where the method colour lives.
    expect(screen.getByText(/dot colour = method/)).toBeInTheDocument()
  })

  it('explains each colour on hover', () => {
    renderWithProviders(<ChartMethodLegend items={ITEMS} onToggle={() => {}} />)
    expect(screen.getByText('Watch (not taken)')).toHaveAttribute(
      'title',
      expect.stringContaining('Neither a buy nor a sell'),
    )
    expect(screen.getByText(/dot colour = method/)).toHaveAttribute(
      'title',
      expect.stringContaining('colour of the method that drew it'),
    )
  })

  it("draws each chip's marker in that method's colour: filled shown, outlined hidden", () => {
    renderWithProviders(<ChartMethodLegend items={ITEMS} onToggle={() => {}} />)

    const glyph = (name: RegExp) =>
      screen.getByRole('button', { name }).querySelector('svg > *') as SVGElement

    // VSA is an arrow (its markers are arrows); every other method is a dot.
    expect(glyph(/VSA rating/).tagName).toBe('path')
    expect(glyph(/Minervini/).tagName).toBe('circle')
    // Shown: a solid dot in the method's colour.
    expect(glyph(/Minervini/).getAttribute('fill')).toBe(PALETTE.methodColors.minervini)
    // Hidden: the same colour, outlined.
    expect(glyph(/VSA V4/).getAttribute('fill')).toBe('none')
    expect(glyph(/VSA V4/).getAttribute('stroke')).toBe(PALETTE.methodColors.vsa4)
  })

  it('shows each method as a toggle chip with its marker count', async () => {
    const onToggle = vi.fn()
    renderWithProviders(<ChartMethodLegend items={ITEMS} onToggle={onToggle} />)

    const vsa = screen.getByRole('button', { name: /VSA rating/ })
    const v4 = screen.getByRole('button', { name: /VSA V4/ })
    expect(vsa).toHaveAttribute('aria-pressed', 'true')
    expect(vsa).toHaveTextContent('7')
    expect(v4).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(v4)
    expect(onToggle).toHaveBeenCalledWith('vsa4')
  })

  it('renders nothing when the chart has no methods', () => {
    const { container } = renderWithProviders(
      <ChartMethodLegend items={[]} onToggle={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
