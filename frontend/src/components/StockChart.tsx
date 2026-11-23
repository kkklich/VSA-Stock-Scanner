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
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import type { Candle, VsaSignal } from '../types'
import { markerColor, useChartPalette, type MarkerType } from '../lib/chartTheme'
import { toChartTime } from '../lib/chartTime'
import type { StockTradeMarker } from '../lib/stockTradeMarkers'

/** Empty slots kept to the right of the newest bar (time-scale `rightOffset`). */
const RIGHT_OFFSET = 4

/** True when this series is intraday — its bars carry a time of day. */
function isIntraday(candles: Candle[]): boolean {
  return candles.length > 0 && candles[0].time.includes('T')
}

/**
 * One trading method's overlay layer on the chart: its historical firings
 * drawn as dots in the method's own `color` (bullish below the bar, bearish
 * above), each with a label coloured by direction. VSA keeps its own arrow
 * markers via the `signals` prop; every OTHER method comes in here. `color` is
 * chosen by the page so the chart and its legend agree.
 */
export interface MethodOverlay {
  methodId: string
  color: string
  /**
   * When true, colour the marker dot itself by direction (green below bar for
   * buys, red above bar for sells) instead of a fixed method colour. Used for
   * the Insider Transactions layer.
   */
  directionalColor?: boolean
  signals: { date: string; label: string; type: MarkerType }[]
}

/**
 * A "watch" marker — a pattern the method looked at and did NOT take — is a
 * square in the method's colour at 60%, so it reads as a quieter note beside
 * the solid dots of its real firings. Appending an alpha pair works on the
 * 6-digit hex values in `chartTheme`; anything else is left as it is.
 */
function muted(color: string): string {
  return /^#[0-9a-f]{6}$/i.test(color) ? `${color}99` : color
}

/**
 * Today's session so far (live prices), drawn after the finished bars as a
 * hollow candle with a grey volume bar: it is still forming, the VSA engine
 * never saw it, and none of the markers are about it.
 */
export interface FormingCandle {
  /** The session date, YYYY-MM-DD — later than every finished bar. */
  time: string
  open: number
  high: number
  low: number
  close: number
  /** Shares traded so far today; null when unknown (then no volume bar). */
  volume: number | null
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
  tradeMarkers,
  forming,
  onSpanSettled,
  preserveViewRef,
}: {
  candles: Candle[]
  signals: VsaSignal[]
  /** Extra per-method overlay layers (Minervini, …); VSA uses `signals`. */
  overlays?: MethodOverlay[]
  tradeMarkers?: StockTradeMarker[]
  /**
   * Today's still-forming candle, drawn after `candles` (daily charts only —
   * the page decides). Ignored unless it is later than the newest candle.
   */
  forming?: FormingCandle | null
  /**
   * Called once the user stops scrolling/zooming the time scale. Lets the page
   * load older history without discarding bars the user is viewing.
   */
  onSpanSettled?: (span: VisibleSpan) => void
  /**
   * When the parent flips this to `true` before loading older history,
   * the chart keeps the exact same bars under the viewport instead of
   * re-fitting — so the range change is seamless, with no "jump". The chart
   * resets it to `false` after each data swap. Left `false` (button clicks,
   * first load, a new ticker) the chart fits the new data to the view.
   */
  preserveViewRef?: MutableRefObject<boolean>
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  const palette = useChartPalette()
  const spanCb = useRef(onSpanSettled)
  spanCb.current = onSpanSettled
  const lastCandlesRef = useRef<Candle[] | null>(null)
  const chartRef = useRef<{
    chart: IChartApi
    candleSeries: ISeriesApi<'Candlestick'>
    volumeSeries: ISeriesApi<'Histogram'>
    markers: ISeriesMarkersPluginApi<Time>
  } | null>(null)

  // Keep the canvas and its interaction state alive until the component unmounts.
  // Data, marker and theme updates are applied to these existing series below.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        fontFamily: 'inherit',
      },
      timeScale: {
        rightOffset: RIGHT_OFFSET,
        shiftVisibleRangeOnNewBar: false,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
      width: el.clientWidth,
      height: el.clientHeight,
    })
    const candleSeries = chart.addSeries(CandlestickSeries, { borderVisible: true })
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } })
    const markers = createSeriesMarkers(candleSeries, [])
    chartRef.current = { chart, candleSeries, volumeSeries, markers }

    let settleTimer: ReturnType<typeof setTimeout> | undefined
    let dragging = false
    let pendingRange: { from: number; to: number } | null = null
    const scheduleSettled = () => {
      clearTimeout(settleTimer)
      if (dragging || !pendingRange) return
      settleTimer = setTimeout(() => {
        if (!pendingRange) return
        spanCb.current?.({
          barsBefore: pendingRange.from,
          visibleBars: pendingRange.to - pendingRange.from,
          totalBars: lastCandlesRef.current?.length ?? 0,
        })
      }, SETTLE_MS)
    }
    const onLogicalRange = (logical: { from: number; to: number } | null) => {
      pendingRange = logical
      scheduleSettled()
    }
    const onPointerDown = () => {
      dragging = true
      clearTimeout(settleTimer)
    }
    const onPointerUp = () => {
      if (!dragging) return
      dragging = false
      scheduleSettled()
    }
    chart.timeScale().subscribeVisibleLogicalRangeChange(onLogicalRange)
    el.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
    const observer = new ResizeObserver(() =>
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }),
    )
    observer.observe(el)
    return () => {
      clearTimeout(settleTimer)
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onLogicalRange)
      el.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      lastCandlesRef.current = null
    }
  }, [])

  useEffect(() => {
    const api = chartRef.current
    if (!api) return
    api.chart.applyOptions({
      layout: { textColor: palette.axisText },
      grid: {
        vertLines: { color: palette.grid },
        horzLines: { color: palette.grid },
      },
      rightPriceScale: { borderColor: palette.scaleBorder },
      timeScale: { borderColor: palette.scaleBorder },
    })
    api.candleSeries.applyOptions({
      upColor: palette.bull,
      downColor: palette.bear,
      wickUpColor: palette.bull,
      wickDownColor: palette.bear,
      borderUpColor: palette.bull,
      borderDownColor: palette.bear,
    })
  }, [palette])

  useEffect(() => {
    const api = chartRef.current
    if (!api) return
    const { chart, candleSeries, volumeSeries } = api
    const previous = lastCandlesRef.current
    const previousRange = chart.timeScale().getVisibleLogicalRange()
    const sameSeries = previous === candles
    const intraday = isIntraday(candles)
    chart.applyOptions({ timeScale: { timeVisible: intraday } })
    const newest = candles.length > 0 ? candles[candles.length - 1].time : null
    const formingBar =
      forming && !intraday && (newest === null || forming.time > newest) ? forming : null
    const formingColor =
      formingBar && formingBar.close < formingBar.open ? palette.bear : palette.bull

    candleSeries.setData([
      ...candles.map((c) => ({
        time: toChartTime(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
      ...(formingBar
        ? [
            {
              time: toChartTime(formingBar.time),
              open: formingBar.open,
              high: formingBar.high,
              low: formingBar.low,
              close: formingBar.close,
              color: 'rgba(0,0,0,0)',
              borderColor: formingColor,
              wickColor: formingColor,
            },
          ]
        : []),
    ])

    volumeSeries.setData([
      ...candles.map((c) => ({
        time: toChartTime(c.time),
        value: c.volume,
        color:
          c.close >= c.open ? palette.bullVolume : palette.bearVolume,
      })),
      // Grey: only part of a day's volume so far, not to be read like a bar.
      ...(formingBar && formingBar.volume !== null
        ? [
            {
              time: toChartTime(formingBar.time),
              value: formingBar.volume,
              color: palette.formingVolume,
            },
          ]
        : []),
    ])
    // Anchor by a shared candle's date. A count difference alone also includes
    // newly appended bars, which would shift the view when a session completes.
    const oldFirst = previous?.[0]?.time
    const newFirst = candles[0]?.time
    const prepended = oldFirst ? candles.findIndex(c => c.time === oldFirst) : -1
    const removed = newFirst && previous ? previous.findIndex(c => c.time === newFirst) : -1
    const offset = prepended >= 0 ? prepended : removed >= 0 ? -removed : null
    const keepView = previousRange && offset !== null && (
      sameSeries || preserveViewRef?.current === true || oldFirst === newFirst
    )
    if (keepView) {
      // Let the library retain its current drag/zoom state when dates did not move.
      // Only a history prepend/removal requires moving logical indices explicitly.
      if (offset !== 0) {
        chart.timeScale().setVisibleLogicalRange({
          from: previousRange.from + offset,
          to: previousRange.to + offset,
        })
      }
    } else {
      chart.timeScale().fitContent()
    }
    if (!sameSeries && preserveViewRef) preserveViewRef.current = false
    lastCandlesRef.current = candles
  }, [candles, forming, palette, preserveViewRef])

  useEffect(() => {
    const api = chartRef.current
    if (!api) return
    // VSA structural markers — bullish below the bar (▲), bearish above (▼).
    // Each marker travels next to `sortKey`, the original API date string, so
    // the merge below can order markers by it: the converted times are strings
    // on a daily chart but numbers on an intraday one, which do not compare the
    // same way. Keeping the key beside the marker rather than inside it means
    // nothing has to be stripped off again before handing it to the chart.
    type SortedMarker = { sortKey: string; marker: SeriesMarker<Time> }

    const vsaMarkers: SortedMarker[] = signals.map((s) => {
      const bull = s.type === 'Bullish'
      return {
        sortKey: s.date,
        marker: {
          time: toChartTime(s.date),
          position: bull ? ('belowBar' as const) : ('aboveBar' as const),
          color: markerColor(s.type, palette),
          shape: bull ? ('arrowUp' as const) : ('arrowDown' as const),
          text: s.signalName,
        },
      }
    })

    // Other methods' markers say two things — which method, and good or bad
    // news — so each is a pair stacked on its bar: a dot in the method's own
    // colour (the same colour as its chip in the legend), then the label in the
    // direction colour, green positive / red negative like the VSA arrows. The
    // label is a size-0 marker, which Lightweight Charts draws as text alone,
    // in the next stack slot after the dot. Bullish below the bar, bearish
    // above. A "watch" — a pattern the method assessed and refused — is a
    // muted square with a grey label: a different shape and no direction
    // colour, so a refused pattern is never read as an entry.
    const overlayMarkers: SortedMarker[] = (overlays ?? []).flatMap((o) =>
      o.signals.flatMap((s) => {
        const time = toChartTime(s.date)
        const position = s.type === 'Bearish' ? ('aboveBar' as const) : ('belowBar' as const)
        const watch = s.type === 'Watch'
        const dotColor = o.directionalColor
          ? markerColor(s.type, palette)
          : watch
            ? muted(o.color)
            : o.color
        return [
          {
            sortKey: s.date,
            marker: {
              time,
              position,
              color: dotColor,
              shape: watch ? ('square' as const) : ('circle' as const),
            },
          },
          {
            sortKey: s.date,
            marker: {
              time,
              position,
              color: markerColor(s.type, palette),
              shape: 'circle' as const,
              size: 0,
              text: s.label,
            },
          },
        ]
      }),
    )

    // Lightweight Charts requires markers in ascending time order; merging the
    // VSA + overlay layers interleaves them, so sort the combined set by the
    // API date string, which is chronological as text in both bar formats.
    // The sort is stable, which keeps each dot directly followed by its label.
    const personalMarkers: SortedMarker[] = (tradeMarkers ?? []).map(trade => {
      const buy = trade.side === 'buy'
      return {
        sortKey: trade.date,
        marker: {
          time: toChartTime(trade.date),
          position: buy ? 'belowBar' : 'aboveBar',
          shape: buy ? 'arrowUp' : 'arrowDown',
          color: markerColor(buy ? 'Bullish' : 'Bearish', palette),
          text: trade.label,
        },
      }
    })
    const markers: SeriesMarker<Time>[] = [...vsaMarkers, ...overlayMarkers, ...personalMarkers]
      .sort((a, b) => a.sortKey.localeCompare(b.sortKey))
      .map((m) => m.marker)
    api.markers.setMarkers(markers)
  }, [signals, overlays, tradeMarkers, palette])

  return <div ref={containerRef} className="h-full w-full" />
}
