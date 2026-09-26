// Today's forming candle on the stock chart (live prices). The library is mocked
// the same way as in StockChart.test.tsx; what is pinned here is that the
// forming candle is drawn AFTER the finished bars, hollow, with a grey volume
// bar — and only when it really is a newer session than the last finished bar.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import type { Candle } from '../types'
import { CHART_THEME } from '../lib/chartTheme'

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

import { StockChart, type FormingCandle } from './StockChart'

const CANDLES: Candle[] = [
  { time: '2026-09-23', open: 10, high: 12, low: 9, close: 11, volume: 1000 },
  { time: '2026-09-24', open: 11, high: 13, low: 10, close: 10, volume: 1500 },
]

const TODAY: FormingCandle = {
  time: '2026-09-25',
  open: 10,
  high: 10.5,
  low: 9.4,
  close: 9.6,
  volume: 400,
}

beforeEach(() => {
  lib.chart.addSeries.mockImplementation((type: unknown) =>
    type === lib.CandlestickSeries ? lib.candleSeries : lib.volumeSeries,
  )
  lib.chart.priceScale.mockReturnValue(lib.priceScale)
  lib.chart.timeScale.mockReturnValue(lib.timeScale)
  lib.createChart.mockReturnValue(lib.chart)
})

describe('StockChart — the forming candle', () => {
  it('is drawn after the finished bars, hollow, in its direction colour', () => {
    render(<StockChart candles={CANDLES} signals={[]} forming={TODAY} />)
    const candles = lib.candleSeries.setData.mock.calls.at(-1)?.[0]
    expect(candles).toHaveLength(3)
    expect(candles?.[2]).toMatchObject({
      time: '2026-09-25',
      close: 9.6,
      color: 'rgba(0,0,0,0)',
      // Down so far today (close under open): the bearish colour.
      borderColor: PALETTE.bear,
      wickColor: PALETTE.bear,
    })
    // The finished bars carry no per-bar styling: they look as they always did.
    expect(candles?.[1]).not.toHaveProperty('color')
  })

  it('has a grey volume bar — only part of a day', () => {
    render(<StockChart candles={CANDLES} signals={[]} forming={TODAY} />)
    const volume = lib.volumeSeries.setData.mock.calls.at(-1)?.[0]
    expect(volume).toHaveLength(3)
    expect(volume?.[2]).toMatchObject({ value: 400, color: PALETTE.formingVolume })
  })

  it('draws no volume bar when the volume is unknown', () => {
    render(<StockChart candles={CANDLES} signals={[]} forming={{ ...TODAY, volume: null }} />)
    expect(lib.candleSeries.setData.mock.calls.at(-1)?.[0]).toHaveLength(3)
    expect(lib.volumeSeries.setData.mock.calls.at(-1)?.[0]).toHaveLength(2)
  })

  it('is ignored once the finished data covers that session', () => {
    render(
      <StockChart
        candles={CANDLES}
        signals={[]}
        forming={{ ...TODAY, time: '2026-09-24' }}
      />,
    )
    expect(lib.candleSeries.setData.mock.calls.at(-1)?.[0]).toHaveLength(2)
  })

  it('leaves the chart as it was without one', () => {
    render(<StockChart candles={CANDLES} signals={[]} />)
    expect(lib.candleSeries.setData.mock.calls.at(-1)?.[0]).toHaveLength(2)
    expect(lib.volumeSeries.setData.mock.calls.at(-1)?.[0]).toHaveLength(2)
  })
})
