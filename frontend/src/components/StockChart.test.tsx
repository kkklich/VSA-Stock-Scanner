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

import { StockChart } from './StockChart'

const CANDLES: Candle[] = [
  { time: '2026-01-01', open: 10, high: 12, low: 9, close: 11, volume: 1000 },
  { time: '2026-01-02', open: 11, high: 13, low: 10, close: 10, volume: 1500 },
  { time: '2026-01-03', open: 10, high: 11, low: 9, close: 11, volume: 900 },
]

const SIGNALS: VsaSignal[] = [
  { date: '2026-01-01', signalName: 'Spring', type: 'Bullish' },
  { date: '2026-01-02', signalName: 'Upthrust', type: 'Bearish' },
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
