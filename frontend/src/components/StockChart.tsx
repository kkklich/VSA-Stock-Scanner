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
import { markerColor, useChartPalette, type MarkerType } from '../lib/chartTheme'
import { toChartTime } from '../lib/chartTime'

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
  forming,
  onSpanSettled,
  preserveViewRef,
}: {
  candles: Candle[]
  signals: VsaSignal[]
  /** Extra per-method overlay layers (Minervini, …); VSA uses `signals`. */
  overlays?: MethodOverlay[]
  /**
   * Today's still-forming candle, drawn after `candles` (daily charts only —
   * the page decides). Ignored unless it is later than the newest candle.
   */
  forming?: FormingCandle | null
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

  // Chart colours for the active theme. Lightweight Charts paints to a canvas
  // and cannot read CSS variables, so a theme change rebuilds the chart (the
  // effect below lists `palette` as a dependency); the visible range is kept,
  // because the candles are the same objects, so the rebuild is invisible
  // apart from the colours.
  const palette = useChartPalette()

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

    // Intraday bars need the time of day on the axis and in the crosshair
    // label; on a daily/weekly chart the date alone is the right label.
    const intraday = isIntraday(candles)

    const chart: IChartApi = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: palette.axisText,
        fontFamily: 'inherit',
      },
      grid: {
        vertLines: { color: palette.grid },
        horzLines: { color: palette.grid },
      },
      rightPriceScale: { borderColor: palette.scaleBorder },
      timeScale: {
        borderColor: palette.scaleBorder,
        rightOffset: RIGHT_OFFSET,
        timeVisible: intraday,
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
      width: el.clientWidth,
      height: el.clientHeight,
    })

    // Today's forming candle, when it really is newer than the finished bars.
    const newest = candles.length > 0 ? candles[candles.length - 1].time : null
    const formingBar =
      forming && !intraday && (newest === null || forming.time > newest) ? forming : null
    const formingColor =
      formingBar && formingBar.close < formingBar.open ? palette.bear : palette.bull

    // Candlesticks (top pane). Borders in the body colours, so a finished
    // candle looks exactly as it always did — the border only shows on the
    // forming candle, which is drawn hollow.
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: palette.bull,
      downColor: palette.bear,
      wickUpColor: palette.bull,
      wickDownColor: palette.bear,
      borderVisible: true,
      borderUpColor: palette.bull,
      borderDownColor: palette.bear,
    })
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

    // Volume histogram pinned to a lower overlay band.
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    })
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
    const markers: SeriesMarker<Time>[] = [...vsaMarkers, ...overlayMarkers]
      .sort((a, b) => a.sortKey.localeCompare(b.sortKey))
      .map((m) => m.marker)
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

    // Watch the CONTAINER, not the window. Lightweight Charts draws onto a
    // fixed-size canvas, so it has to be told when its box changes — and the
    // box changes plenty without the window doing anything: the sidebar drawer
    // opening below `lg`, a card above the chart growing by a line, the
    // right-hand column reflowing when the fundamentals land. Each of those
    // used to leave the canvas at its old width until the user happened to
    // resize the browser.
    const applySize = () =>
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight })
    const observer = new ResizeObserver(applySize)
    observer.observe(el)

    return () => {
      clearTimeout(settleTimer)
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onLogicalRange)
      observer.disconnect()
      chart.remove()
    }
  }, [candles, signals, overlays, forming, preserveViewRef, palette])

  return <div ref={containerRef} className="h-full w-full" />
}
