// Interactive candlestick + volume chart with VSA signal markers, built on
// TradingView Lightweight Charts (v5 API). See DOCUMENTATION.md §4 Component 2.

import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type IChartApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import type { Candle, VsaSignal } from '../types'

const BULL = '#10B981'
const BEAR = '#F43F5E'

/** What the user is currently looking at, reported after they stop scrolling. */
export type VisibleSpan = {
  /** Loaded bars hidden to the left; negative = empty space past the oldest bar. */
  barsBefore: number
  /** How many bars fit in the viewport right now. */
  visibleBars: number
  /** How many bars are loaded in total. */
  totalBars: number
}

/** How long the view must sit still before `onSpanSettled` fires (ms). */
const SETTLE_MS = 220

export function StockChart({
  candles,
  signals,
  onSpanSettled,
}: {
  candles: Candle[]
  signals: VsaSignal[]
  /**
   * Called once the user stops scrolling/zooming the time scale. Lets the page
   * grow or shrink the loaded time range to match what they scrolled to.
   */
  onSpanSettled?: (span: VisibleSpan) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Keep the latest callback without re-creating the chart when it changes.
  const spanCb = useRef(onSpanSettled)
  spanCb.current = onSpanSettled

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart: IChartApi = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
        fontFamily: 'inherit',
      },
      grid: {
        vertLines: { color: 'rgba(148,163,184,0.06)' },
        horzLines: { color: 'rgba(148,163,184,0.06)' },
      },
      rightPriceScale: { borderColor: 'rgba(148,163,184,0.15)' },
      timeScale: { borderColor: 'rgba(148,163,184,0.15)', rightOffset: 4 },
      crosshair: { mode: 0 },
      width: el.clientWidth,
      height: el.clientHeight,
    })

    // Candlesticks (top pane).
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: BULL,
      downColor: BEAR,
      wickUpColor: BULL,
      wickDownColor: BEAR,
      borderVisible: false,
    })
    candleSeries.setData(
      candles.map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    )

    // Volume histogram pinned to a lower overlay band.
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    })
    volumeSeries.setData(
      candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color:
          c.close >= c.open ? 'rgba(16,185,129,0.5)' : 'rgba(244,63,94,0.5)',
      }))
    )

    // VSA structural markers — bullish below the bar (▲), bearish above (▼).
    const markers: SeriesMarker<Time>[] = signals.map((s) => {
      const bull = s.type === 'Bullish'
      return {
        time: s.date as Time,
        position: bull ? 'belowBar' : 'aboveBar',
        color: bull ? BULL : BEAR,
        shape: bull ? 'arrowUp' : 'arrowDown',
        text: s.signalName,
      }
    })
    createSeriesMarkers(candleSeries, markers)

    chart.timeScale().fitContent()

    // Report the visible span after the user stops scrolling/zooming, so the
    // page can load a wider or narrower slice of history to match.
    let settleTimer: ReturnType<typeof setTimeout> | undefined
    const onLogicalRange = (
      logical: { from: number; to: number } | null,
    ) => {
      if (!logical) return
      clearTimeout(settleTimer)
      settleTimer = setTimeout(() => {
        spanCb.current?.({
          barsBefore: logical.from,
          visibleBars: logical.to - logical.from,
          totalBars: candles.length,
        })
      }, SETTLE_MS)
    }
    chart.timeScale().subscribeVisibleLogicalRangeChange(onLogicalRange)

    const onResize = () =>
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight })
    window.addEventListener('resize', onResize)

    return () => {
      clearTimeout(settleTimer)
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onLogicalRange)
      window.removeEventListener('resize', onResize)
      chart.remove()
    }
  }, [candles, signals])

  return <div ref={containerRef} className="h-full w-full" />
}
