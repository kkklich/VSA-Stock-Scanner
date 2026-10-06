// Colours for everything the app paints in JavaScript rather than in CSS:
// the TradingView candlestick chart, the sector-heatmap tiles and the inline
// SVG mini-charts. Those cannot use Tailwind's variables, so each theme's
// values live here — one place to look when a chart colour is wrong.
//
// The dark column is the app's original palette, unchanged. The light column
// uses the darker end of each hue so a thin line or a small marker still reads
// on a white card (the same reasoning as the accent overrides in index.css).

import { useResolvedTheme, type ResolvedTheme } from './theme'

export interface ChartPalette {
  /**
   * Bullish / strength (VSA convention: emerald). On the stock chart it is
   * also every positive signal: VSA's up-arrows and every method's label.
   */
  bull: string
  /** Bearish / weakness (VSA convention: rose) — and every negative signal. */
  bear: string
  /**
   * A signal that is neither positive nor negative: a "watch", i.e. a pattern
   * a method assessed and refused. Grey, and readable as label text.
   */
  neutral: string
  /** Volume bars — the same two hues, translucent. */
  bullVolume: string
  bearVolume: string
  /**
   * Volume of today's still-forming candle (live prices): grey, because it is
   * only part of a day's volume and must not be read like a finished bar's.
   */
  formingVolume: string
  /** Axis labels on the price/time scales. */
  axisText: string
  /** Chart grid lines and the price/time scale borders. */
  grid: string
  scaleBorder: string
  /**
   * Each trading method's own dot colour on the stock chart, keyed by method
   * id — never by position, or removing one method would silently recolour
   * every method after it. No green and no red: those two say positive /
   * negative on the same chart, so a method dot in either would be read as a
   * verdict.
   */
  methodColors: Record<string, string>
  /** For a method added since `methodColors` was written, in display order. */
  spareMethodColors: string[]
  /** Sector heatmap: the negative → neutral → positive tile ramp. */
  heatmapNegative: [number, number, number]
  heatmapNeutral: [number, number, number]
  heatmapPositive: [number, number, number]
  /** Heatmap tile with no value for the selected horizon. */
  heatmapMissing: string
  /** Text drawn on top of a coloured heatmap tile. */
  heatmapTileText: string
  heatmapTileSubText: string
  /** Track behind a progress ring / gauge. */
  gaugeTrack: string
  /** Neutral stroke for axes in the small inline SVG charts. */
  svgAxis: string
}

const DARK: ChartPalette = {
  bull: '#10B981',
  bear: '#F43F5E',
  neutral: '#94A3B8', // slate-400, 7.0:1 on the card
  bullVolume: 'rgba(16,185,129,0.5)',
  bearVolume: 'rgba(244,63,94,0.5)',
  formingVolume: 'rgba(148,163,184,0.35)',
  axisText: '#94a3b8',
  grid: 'rgba(148,163,184,0.06)',
  scaleBorder: 'rgba(148,163,184,0.15)',
  methodColors: {
    minervini: '#F59E0B', // amber
    breakout: '#6366F1', // indigo
    glinicki: '#E879F9', // fuchsia (VSA V1; was pink — too close to the red)
    vsa3: '#A855F7', // purple
    vsa4: '#F97316', // orange (was lime — too close to the positive green)
    weinstein: '#3B82F6', // blue
    pocket_pivot: '#06B6D4', // cyan (the first spare, now fixed to it)
  },
  spareMethodColors: ['#7DD3FC', '#FDE047'], // sky, light yellow
  heatmapNegative: [244, 63, 94], // rose-500
  heatmapNeutral: [51, 65, 85], // slate-700
  heatmapPositive: [16, 185, 129], // emerald-500
  heatmapMissing: '#1E293B', // slate-800
  heatmapTileText: 'rgba(255,255,255,0.95)',
  heatmapTileSubText: 'rgba(255,255,255,0.75)',
  gaugeTrack: '#1e293b',
  svgAxis: '#e2e8f0',
}

const LIGHT: ChartPalette = {
  bull: '#047857', // emerald-700
  bear: '#BE123C', // rose-700
  neutral: '#64748B', // slate-500, 4.8:1 on white
  bullVolume: 'rgba(4,120,87,0.35)',
  bearVolume: 'rgba(190,18,60,0.35)',
  formingVolume: 'rgba(100,116,139,0.30)',
  axisText: '#64748b',
  grid: 'rgba(71,85,105,0.10)',
  scaleBorder: 'rgba(71,85,105,0.25)',
  // The 700 shades that keep a dot legible on white also squeeze neighbouring
  // hues together, so the warm pair is gold vs orange (amber-700 is brown-
  // orange, too close to orange-600) and V1 is a brighter magenta than V3.
  methodColors: {
    minervini: '#A16207', // yellow-700 (gold), 4.9:1 on white
    breakout: '#4338CA', // indigo-700
    glinicki: '#C026D3', // fuchsia-600, 4.7:1
    vsa3: '#7E22CE', // purple-700
    vsa4: '#EA580C', // orange-600
    weinstein: '#1D4ED8', // blue-700
    pocket_pivot: '#0E7490', // cyan-700 (the first spare, now fixed to it)
  },
  spareMethodColors: ['#0369A1', '#B45309'], // sky-700, amber-700
  // Tiles sit on a white page and carry white text, so every step of the ramp
  // — including the neutral middle — stays dark enough to read.
  heatmapNegative: [225, 29, 72], // rose-600
  heatmapNeutral: [100, 116, 139], // slate-500
  heatmapPositive: [5, 150, 105], // emerald-600
  // Warm grey, so "no data for this horizon" cannot be mistaken for a neutral
  // reading on the (cool grey) middle of the ramp.
  heatmapMissing: '#78716C', // stone-500
  heatmapTileText: 'rgba(255,255,255,0.98)',
  heatmapTileSubText: 'rgba(255,255,255,0.85)',
  gaugeTrack: '#e2e8f0',
  svgAxis: '#475569',
}

export const CHART_THEME: Record<ResolvedTheme, ChartPalette> = {
  dark: DARK,
  light: LIGHT,
}

export function chartPalette(theme: ResolvedTheme): ChartPalette {
  return CHART_THEME[theme]
}

/** Which way a stock-chart signal points. */
export type MarkerType = 'Bullish' | 'Bearish' | 'Watch'

/**
 * The colour that says whether a stock-chart signal is good or bad news,
 * whichever trading method drew it: green = bullish (positive), red = bearish
 * (negative), grey = a "watch" — a pattern the method assessed and refused,
 * which is neither. It paints VSA's arrows and every method's label; the dot
 * beside a method's label keeps the method's own colour, so one glance gives
 * both the verdict and who gave it. The chart and its colour key both call
 * this, so they cannot disagree.
 */
export function markerColor(type: MarkerType, palette: ChartPalette): string {
  if (type === 'Bullish') return palette.bull
  if (type === 'Bearish') return palette.bear
  return palette.neutral
}

/**
 * Each trading method's dot colour, for the methods on one chart (in display
 * order): its own `methodColors` entry, or — for a method added since that
 * list was written — the next spare, so a new method still gets a colour
 * without a frontend change (the spares repeat only past their count).
 */
export function methodColorsFor(
  methodIds: string[],
  palette: ChartPalette,
): Record<string, string> {
  const colors: Record<string, string> = {}
  let spare = 0
  for (const id of methodIds) {
    colors[id] =
      palette.methodColors[id] ??
      palette.spareMethodColors[spare++ % palette.spareMethodColors.length]
  }
  return colors
}

/** The active theme's chart palette; re-renders the caller when it changes. */
export function useChartPalette(): ChartPalette {
  return CHART_THEME[useResolvedTheme()]
}
