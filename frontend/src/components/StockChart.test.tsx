// Component test for the candlestick chart. TradingView Lightweight Charts needs
// a real canvas, which jsdom does not provide, so the library is fully mocked.
// The test verifies StockChart's contract with it: a chart is built once, the
// candle + volume series receive the mapped bars, and each VSA signal becomes a
// correctly-oriented marker — bullish below the bar (▲), bearish above (▼).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import type { Candle, VsaSignal } from '../types'

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

import { StockChart, toChartTime } from './StockChart'

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
    expect(bull).toMatchObject({ position: 'belowBar', shape: 'arrowUp', text: 'Spring' })
    expect(bear).toMatchObject({ position: 'aboveBar', shape: 'arrowDown', text: 'Upthrust' })
  })

  it('adds overlay markers as coloured circles, time-sorted with VSA', () => {
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
      Array<{ time: string; position: string; shape: string; text: string; color: string }>,
    ]
    // Two VSA arrows + one overlay circle, sorted oldest → newest by date.
    expect(markers).toHaveLength(3)
    expect(markers.map((m) => m.time)).toEqual(['2026-01-01', '2026-01-02', '2026-01-03'])
    const overlay = markers[2]
    expect(overlay).toMatchObject({
      shape: 'circle',
      position: 'belowBar',
      text: 'Trend Template',
      color: '#F59E0B',
    })
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
      Array<{ time: number; text: string; sortKey?: string }>,
    ]
    expect(markers.map((m) => m.text)).toEqual(['SOW', 'Demo', 'SOS'])
    expect(markers.map((m) => m.time)).toEqual(
      [...markers.map((m) => m.time)].sort((a, b) => a - b),
    )
    // The internal ordering key must not leak into the charting library.
    expect(markers[0]).not.toHaveProperty('sortKey')
  })
})
