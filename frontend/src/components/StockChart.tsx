// Interactive candlestick + volume chart with VSA signal markers, built on
// TradingView Lightweight Charts (v5 API). See DOCUMENTATION.md §4 Component 2.

import { useEffect, useRef, type MutableRefObject } from 'react'
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

/** Empty slots kept to the right of the newest bar (time-scale `rightOffset`). */
const RIGHT_OFFSET = 4

/**
 * One trading method's overlay layer on the chart: its historical firings
 * drawn as coloured circle markers (bullish below the bar, bearish above), so
 * several methods can be read side by side and told apart by colour. VSA keeps
 * its own arrow markers via the `signals` prop; every OTHER method comes in
 * here. `color` is chosen by the page so the chart and its legend agree.
 */
export interface MethodOverlay {
  methodId: string
  color: string
  signals: { date: string; label: string; type: 'Bullish' | 'Bearish' }[]
}

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
  overlays,
  onSpanSettled,
  preserveViewRef,
}: {
  candles: Candle[]
  signals: VsaSignal[]
  /** Extra per-method overlay layers (Minervini, …); VSA uses `signals`. */
  overlays?: MethodOverlay[]
  /**
   * Called once the user stops scrolling/zooming the time scale. Lets the page
   * grow or shrink the loaded time range to match what they scrolled to.
   */
  onSpanSettled?: (span: VisibleSpan) => void
  /**
   * When the parent flips this to `true` right before it swaps in a wider or
   * narrower slice of history (because the user scrolled/zoomed off the edge),
   * the chart keeps the exact same bars under the viewport instead of
   * re-fitting — so the range change is seamless, with no "jump". The chart
   * resets it to `false` after each data swap. Left `false` (button clicks,
   * first load, a new ticker) the chart fits the new data to the view.
   */
  preserveViewRef?: MutableRefObject<boolean>
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Keep the latest callback without re-creating the chart when it changes.
  const spanCb = useRef(onSpanSettled)
  spanCb.current = onSpanSettled

  // Remembered across chart rebuilds so a data swap can restore the same view
  // instead of snapping to fit. `lastRange` tracks where the user is looking
  // (updated on every scroll/zoom); the counts identify the series it belongs
  // to so we only reuse it for the same stock.
  const lastRangeRef = useRef<{ from: number; to: number } | null>(null)
  const lastBarCountRef = useRef(0)
  const lastCandlesRef = useRef<Candle[] | null>(null)

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
      timeScale: { borderColor: 'rgba(148,163,184,0.15)', rightOffset: RIGHT_OFFSET },
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
      })),
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
      })),
    )

    // VSA structural markers — bullish below the bar (▲), bearish above (▼).
    const vsaMarkers: SeriesMarker<Time>[] = signals.map((s) => {
      const bull = s.type === 'Bullish'
      return {
        time: s.date as Time,
        position: bull ? 'belowBar' : 'aboveBar',
        color: bull ? BULL : BEAR,
        shape: bull ? 'arrowUp' : 'arrowDown',
        text: s.signalName,
      }
    })

    // Other methods' markers — coloured circles so each method reads as its
    // own layer (bullish below the bar, bearish above), told apart by colour.
    const overlayMarkers: SeriesMarker<Time>[] = (overlays ?? []).flatMap((o) =>
      o.signals.map((s) => {
        const bull = s.type === 'Bullish'
        return {
          time: s.date as Time,
          position: bull ? ('belowBar' as const) : ('aboveBar' as const),
          color: o.color,
          shape: 'circle' as const,
          text: s.label,
        }
      }),
    )

    // Lightweight Charts requires markers in ascending time order; merging the
    // VSA + overlay layers interleaves them, so sort the combined set by date
    // (the `time` values are YYYY-MM-DD strings, which sort lexicographically).
    const markers: SeriesMarker<Time>[] = [...vsaMarkers, ...overlayMarkers].sort(
      (a, b) => String(a.time).localeCompare(String(b.time)),
    )
    createSeriesMarkers(candleSeries, markers)

    // Choose the initial view for this freshly built chart. Setting the range
    // (or fitting) here — in the same synchronous block as createChart/setData
    // — is the layout that reliably sticks; deferring it to a later effect does
    // not, because setData re-applies a default view on the next frame.
    const prevRange = lastRangeRef.current
    const prevCount = lastBarCountRef.current
    const sameSeries = lastCandlesRef.current === candles // only signals changed
    const keepView =
      prevRange != null &&
      prevCount > 0 &&
      candles.length > 0 &&
      (preserveViewRef?.current === true || sameSeries)

    if (keepView && prevRange) {
      // A range change adds (or removes) `delta` bars at the OLD end of the
      // series; the newest bar is unchanged. Shifting the visible range by
      // `delta` keeps the same bars under the viewport (and slides freshly
      // loaded history into the margin the user zoomed into). `delta` is 0 when
      // only the signals changed, so the view is simply held in place.
      const delta = candles.length - prevCount
      chart.timeScale().setVisibleLogicalRange({
        from: prevRange.from + delta,
        to: prevRange.to + delta,
      })
    } else {
      chart.timeScale().fitContent()
    }
    // Consume the one-shot preserve request only once the candles have actually
    // swapped. Widening the range also widens the signal context window, which
    // changes `signals` and re-runs this effect one render BEFORE the new
    // candles arrive; consuming the flag on that early run would drop it before
    // the data swap it was meant for, and the swap would snap to fit.
    if (!sameSeries && preserveViewRef) preserveViewRef.current = false
    lastBarCountRef.current = candles.length
    lastCandlesRef.current = candles

    // Track the visible range as the user moves it, and report the settled span
    // so the page can load a wider or narrower slice of history to match.
    let settleTimer: ReturnType<typeof setTimeout> | undefined
    const onLogicalRange = (
      logical: { from: number; to: number } | null,
    ) => {
      if (!logical) return
      lastRangeRef.current = { from: logical.from, to: logical.to }
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
  }, [candles, signals, overlays, preserveViewRef])

  return <div ref={containerRef} className="h-full w-full" />
}
