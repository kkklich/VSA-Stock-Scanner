// Component test for the candlestick chart. TradingView Lightweight Charts needs
// a real canvas, which jsdom does not provide, so the library is fully mocked.
// The test verifies StockChart's contract with it: a chart is built once, the
// candle + volume series receive the mapped bars, and each VSA signal becomes a
// correctly-oriented marker — bullish below the bar (▲), bearish above (▼) —
// coloured by direction, as is every other method's marker.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import type { Candle, VsaSignal } from '../types'
import { CHART_THEME, methodColorsFor } from '../lib/chartTheme'

// The app's default theme, which is what the chart resolves to under jsdom.
const PALETTE = CHART_THEME.dark

const lib = vi.hoisted(() => {
  const candleSeries = { setData: vi.fn() }
  const volumeSeries = { setData: vi.fn() }
  const priceScale = { applyOptions: vi.fn() }
  const timeScale = {
    fitContent: vi.fn(),
    setVisibleLogicalRange: vi.fn(),
    subscribeVisibleLogicalRangeChange: vi.fn(),
    unsubscribeVisibleLogicalRangeChange: vi.fn(),
  }
  const CandlestickSeries = { kind: 'candles' }
  const HistogramSeries = { kind: 'histogram' }
  const chart = {
    addSeries: vi.fn(),
    priceScale: vi.fn(() => priceScale),
    timeScale: vi.fn(() => timeScale),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  }
  return {
    createChart: vi.fn(),
    createSeriesMarkers: vi.fn(),
    CandlestickSeries,
    HistogramSeries,
    ColorType: { Solid: 'solid' },
    candleSeries,
    volumeSeries,
    priceScale,
    timeScale,
    chart,
  }
})

vi.mock('lightweight-charts', () => ({
  createChart: lib.createChart,
  createSeriesMarkers: lib.createSeriesMarkers,
  CandlestickSeries: lib.CandlestickSeries,
  HistogramSeries: lib.HistogramSeries,
  ColorType: lib.ColorType,
}))

import { StockChart } from './StockChart'
import { toChartTime } from '../lib/chartTime'

const CANDLES: Candle[] = [
  { time: '2026-01-01', open: 10, high: 12, low: 9, close: 11, volume: 1000 },
  { time: '2026-01-02', open: 11, high: 13, low: 10, close: 10, volume: 1500 },
  { time: '2026-01-03', open: 10, high: 11, low: 9, close: 11, volume: 900 },
]

const SIGNALS: VsaSignal[] = [
  { date: '2026-01-01', signalName: 'Spring', type: 'Bullish' },
  { date: '2026-01-02', signalName: 'Upthrust', type: 'Bearish' },
]

// Intraday bars: full ISO timestamps in the exchange's own timezone.
const INTRADAY_CANDLES: Candle[] = [
  { time: '2026-09-04T09:00:00+02:00', open: 10, high: 12, low: 9, close: 11, volume: 1000 },
  { time: '2026-09-04T13:00:00+02:00', open: 11, high: 13, low: 10, close: 10, volume: 1500 },
  { time: '2026-09-07T09:00:00+02:00', open: 10, high: 11, low: 9, close: 11, volume: 900 },
]

beforeEach(() => {
  // (Re)establish implementations each test — the suite's restoreMocks setting
  // would otherwise clear them after the first test.
  lib.chart.addSeries.mockImplementation((type: unknown) =>
    type === lib.CandlestickSeries ? lib.candleSeries : lib.volumeSeries,
  )
  lib.chart.priceScale.mockReturnValue(lib.priceScale)
  lib.chart.timeScale.mockReturnValue(lib.timeScale)
  lib.createChart.mockReturnValue(lib.chart)
})

describe('StockChart', () => {
  it('builds the chart once and feeds both series the mapped bars', () => {
    render(<StockChart candles={CANDLES} signals={SIGNALS} />)

    expect(lib.createChart).toHaveBeenCalledTimes(1)
    // One candle series + one volume series.
    expect(lib.chart.addSeries).toHaveBeenCalledTimes(2)

    const candleData = lib.candleSeries.setData.mock.calls.at(-1)?.[0]
    expect(candleData).toHaveLength(CANDLES.length)
    expect(candleData?.[0]).toMatchObject({ time: '2026-01-01', open: 10, close: 11 })

    const volumeData = lib.volumeSeries.setData.mock.calls.at(-1)?.[0]
    expect(volumeData).toHaveLength(CANDLES.length)
  })

  it('maps each VSA signal to an oriented marker', () => {
    render(<StockChart candles={CANDLES} signals={SIGNALS} />)

    expect(lib.createSeriesMarkers).toHaveBeenCalledTimes(1)
    const [series, markers] = lib.createSeriesMarkers.mock.calls[0] as [
      unknown,
      Array<{ position: string; shape: string; text: string }>,
    ]
    expect(series).toBe(lib.candleSeries)
    expect(markers).toHaveLength(SIGNALS.length)

    const [bull, bear] = markers
    expect(bull).toMatchObject({
      position: 'belowBar',
      shape: 'arrowUp',
      text: 'Spring',
      color: PALETTE.bull,
    })
    expect(bear).toMatchObject({
      position: 'aboveBar',
      shape: 'arrowDown',
      text: 'Upthrust',
      color: PALETTE.bear,
    })
  })

  it('adds each overlay signal as a dot plus its label, time-sorted with VSA', () => {
    render(
      <StockChart
        candles={CANDLES}
        signals={SIGNALS}
        overlays={[
          {
            methodId: 'minervini',
            color: '#F59E0B',
            signals: [{ date: '2026-01-03', label: 'Trend Template', type: 'Bullish' }],
          },
        ]}
      />,
    )

    const [, markers] = lib.createSeriesMarkers.mock.calls.at(-1) as [
      unknown,
      Array<{ time: string; position: string; shape: string; text?: string; size?: number }>,
    ]
    // Two VSA arrows + the overlay's dot and label, sorted oldest → newest.
    expect(markers).toHaveLength(4)
    expect(markers.map((m) => m.time)).toEqual([
      '2026-01-01',
      '2026-01-02',
      '2026-01-03',
      '2026-01-03',
    ])
    const [dot, label] = markers.slice(2)
    // The dot draws the shape and carries no text; the label is a size-0
    // marker, which the library draws as text alone in the next stack slot.
    expect(dot).toMatchObject({ shape: 'circle', position: 'belowBar' })
    expect(dot.text).toBeUndefined()
    expect(label).toMatchObject({ position: 'belowBar', size: 0, text: 'Trend Template' })
  })

  it("draws a method's dot in its own colour and its label by direction", () => {
    // Two questions, two colours: WHICH method (the dot, matching its legend
    // chip) and GOOD OR BAD news (the label — green positive, red negative,
    // exactly like the VSA arrows).
    render(
      <StockChart
        candles={CANDLES}
        signals={SIGNALS}
        overlays={[
          {
            methodId: 'minervini',
            color: '#F59E0B',
            signals: [{ date: '2026-01-03', label: 'Trend Template', type: 'Bullish' }],
          },
          {
            methodId: 'vsa4',
            color: '#F97316',
            signals: [
              { date: '2026-01-01', label: 'Stopping Volume → No Supply', type: 'Bullish' },
              { date: '2026-01-02', label: 'Two Bar Reversal → No Demand', type: 'Bearish' },
            ],
          },
        ]}
      />,
    )

    const [, markers] = lib.createSeriesMarkers.mock.calls.at(-1) as [
      unknown,
      Array<{ position: string; shape: string; text?: string; color: string; size?: number }>,
    ]
    const dotBefore = (text: string) => markers[markers.findIndex((m) => m.text === text) - 1]
    const labelOf = (text: string) => markers.find((m) => m.text === text)

    // Positive: VSA's arrow and both methods' labels share the one green…
    for (const text of ['Spring', 'Trend Template', 'Stopping Volume → No Supply']) {
      expect(labelOf(text)?.color).toBe(PALETTE.bull)
    }
    // …negative: VSA's arrow and V4's label share the one red, above the bar.
    for (const text of ['Upthrust', 'Two Bar Reversal → No Demand']) {
      expect(labelOf(text)).toMatchObject({ color: PALETTE.bear, position: 'aboveBar' })
    }
    // Each dot sits right before its label, in its method's colour, same side.
    expect(dotBefore('Trend Template')).toMatchObject({ shape: 'circle', color: '#F59E0B' })
    expect(dotBefore('Stopping Volume → No Supply')).toMatchObject({ color: '#F97316' })
    expect(dotBefore('Two Bar Reversal → No Demand')).toMatchObject({
      shape: 'circle',
      color: '#F97316',
      position: 'aboveBar',
    })
  })

  it('draws a near-miss ("Watch") as a muted square with a grey label', () => {
    // A pattern the method assessed and refused. It must be visible — that is
    // the point of it — but must never look like an entry, so it gets its own
    // shape, a faded method colour, and a label in neither direction's colour.
    render(
      <StockChart
        candles={CANDLES}
        signals={[]}
        overlays={[
          {
            methodId: 'vsa3',
            color: '#A855F7',
            signals: [
              { date: '2026-01-02', label: 'Hammer + Shakeout · no sequence', type: 'Watch' },
              { date: '2026-01-03', label: 'Hammer + Test', type: 'Bullish' },
            ],
          },
        ]}
      />,
    )

    const [, markers] = lib.createSeriesMarkers.mock.calls.at(-1) as [
      unknown,
      Array<{ position: string; shape: string; text?: string; color: string }>,
    ]
    const [watchDot, watchLabel, dot, label] = markers
    expect(watchDot).toMatchObject({ shape: 'square', position: 'belowBar', color: '#A855F799' })
    expect(watchLabel).toMatchObject({
      text: 'Hammer + Shakeout · no sequence',
      color: PALETTE.neutral,
    })
    expect(PALETTE.neutral).not.toBe(PALETTE.bull)
    expect(PALETTE.neutral).not.toBe(PALETTE.bear)
    // The real firing: a solid dot in the method's colour, a green label.
    expect(dot).toMatchObject({ shape: 'circle', color: '#A855F7' })
    expect(label).toMatchObject({ text: 'Hammer + Test', color: PALETTE.bull })
  })

  it('keeps method dot colours distinct and clear of the green and red', () => {
    // A dot in either colour would be read as a verdict rather than a method.
    for (const palette of [CHART_THEME.dark, CHART_THEME.light]) {
      const all = [...Object.values(palette.methodColors), ...palette.spareMethodColors]
      expect(all).not.toContain(palette.bull)
      expect(all).not.toContain(palette.bear)
      expect(all).not.toContain(palette.neutral)
      expect(new Set(all).size).toBe(all.length)
    }
  })

  it('gives each method a fixed colour that survives another being removed', () => {
    // Colours used to be handed out by position, so dropping one method
    // silently recoloured every method after it.
    const withAll = methodColorsFor(['minervini', 'breakout', 'vsa3', 'weinstein'], PALETTE)
    const withoutOne = methodColorsFor(['minervini', 'vsa3', 'weinstein'], PALETTE)
    expect(withoutOne.vsa3).toBe(withAll.vsa3)
    expect(withoutOne.weinstein).toBe(withAll.weinstein)
    expect(withAll.vsa3).toBe(PALETTE.methodColors.vsa3)
    // A method the palette has never heard of still gets a colour of its own.
    const withNew = methodColorsFor(['minervini', 'brand-new', 'newer'], PALETTE)
    expect(withNew['brand-new']).toBe(PALETTE.spareMethodColors[0])
    expect(withNew.newer).toBe(PALETTE.spareMethodColors[1])
  })

  it('tears the chart down on unmount', () => {
    const { unmount } = render(<StockChart candles={CANDLES} signals={SIGNALS} />)
    unmount()
    expect(lib.chart.remove).toHaveBeenCalledTimes(1)
    expect(lib.timeScale.unsubscribeVisibleLogicalRangeChange).toHaveBeenCalled()
  })
})

describe('toChartTime', () => {
  it('passes a daily bar through as a business-day string', () => {
    expect(toChartTime('2026-01-01')).toBe('2026-01-01')
  })

  it('renders an intraday bar at the time it actually traded', () => {
    // Lightweight Charts has no timezone support and labels every timestamp as
    // UTC, so the exchange's offset is folded in. A bar that traded at 13:00 in
    // Warsaw must therefore read back as 13:00, not 11:00.
    const seconds = toChartTime('2026-09-04T13:00:00+02:00') as number
    expect(new Date(seconds * 1000).toISOString()).toBe('2026-09-04T13:00:00.000Z')
  })

  it('keeps the label right across a daylight-saving change', () => {
    // Warsaw is +01:00 in March and +02:00 in September; 09:00 is 09:00 in both.
    const winter = toChartTime('2026-03-02T09:00:00+01:00') as number
    const summer = toChartTime('2026-09-02T09:00:00+02:00') as number
    expect(new Date(winter * 1000).toISOString()).toBe('2026-03-02T09:00:00.000Z')
    expect(new Date(summer * 1000).toISOString()).toBe('2026-09-02T09:00:00.000Z')
  })

  it('handles a UTC (Z) timestamp without shifting it', () => {
    const seconds = toChartTime('2026-09-04T13:00:00Z') as number
    expect(new Date(seconds * 1000).toISOString()).toBe('2026-09-04T13:00:00.000Z')
  })

  it('orders intraday bars chronologically', () => {
    const times = INTRADAY_CANDLES.map((c) => toChartTime(c.time) as number)
    expect(times).toEqual([...times].sort((a, b) => a - b))
  })
})

describe('StockChart on an intraday series', () => {
  it('converts bars to timestamps and turns on the clock in the axis', () => {
    render(<StockChart candles={INTRADAY_CANDLES} signals={[]} />)

    const options = lib.createChart.mock.calls.at(-1)?.[1] as {
      timeScale: { timeVisible: boolean; secondsVisible: boolean }
    }
    expect(options.timeScale.timeVisible).toBe(true)
    expect(options.timeScale.secondsVisible).toBe(false)

    const candleData = lib.candleSeries.setData.mock.calls.at(-1)?.[0] as Array<{
      time: number
    }>
    expect(candleData).toHaveLength(INTRADAY_CANDLES.length)
    expect(typeof candleData[0].time).toBe('number')
  })

  it('leaves the clock off on a daily series', () => {
    render(<StockChart candles={CANDLES} signals={SIGNALS} />)
    const options = lib.createChart.mock.calls.at(-1)?.[1] as {
      timeScale: { timeVisible: boolean }
    }
    expect(options.timeScale.timeVisible).toBe(false)
  })

  it('sorts merged intraday markers by time, and strips the sort key', () => {
    render(
      <StockChart
        candles={INTRADAY_CANDLES}
        signals={[
          { date: '2026-09-07T09:00:00+02:00', signalName: 'SOS', type: 'Bullish' },
          { date: '2026-09-04T09:00:00+02:00', signalName: 'SOW', type: 'Bearish' },
        ]}
        overlays={[
          {
            methodId: 'demo',
            color: '#F59E0B',
            signals: [
              { date: '2026-09-04T13:00:00+02:00', label: 'Demo', type: 'Bullish' },
            ],
          },
        ]}
      />,
    )

    const [, markers] = lib.createSeriesMarkers.mock.calls.at(-1) as [
      unknown,
      Array<{ time: number; text?: string; sortKey?: string }>,
    ]
    // The overlay's dot carries no text; its label follows it directly.
    expect(markers.map((m) => m.text)).toEqual(['SOW', undefined, 'Demo', 'SOS'])
    expect(markers.map((m) => m.time)).toEqual(
      [...markers.map((m) => m.time)].sort((a, b) => a - b),
    )
    // The internal ordering key must not leak into the charting library.
    expect(markers[0]).not.toHaveProperty('sortKey')
  })
})
