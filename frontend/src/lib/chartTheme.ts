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
  /** Bullish / strength (VSA convention: emerald). */
  bull: string
  /** Bearish / weakness (VSA convention: rose). */
  bear: string
  /** Volume bars — the same two hues, translucent. */
  bullVolume: string
  bearVolume: string
  /** Axis labels on the price/time scales. */
  axisText: string
  /** Chart grid lines and the price/time scale borders. */
  grid: string
  scaleBorder: string
  /** Marker colours for the per-method overlay layers, in order. */
  methodColors: string[]
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
  bullVolume: 'rgba(16,185,129,0.5)',
  bearVolume: 'rgba(244,63,94,0.5)',
  axisText: '#94a3b8',
  grid: 'rgba(148,163,184,0.06)',
  scaleBorder: 'rgba(148,163,184,0.15)',
  methodColors: [
    '#F59E0B', // amber
    '#6366F1', // indigo
    '#EC4899', // pink
    '#06B6D4', // cyan
    '#A855F7', // purple
    '#84CC16', // lime
  ],
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
  bullVolume: 'rgba(4,120,87,0.35)',
  bearVolume: 'rgba(190,18,60,0.35)',
  axisText: '#64748b',
  grid: 'rgba(71,85,105,0.10)',
  scaleBorder: 'rgba(71,85,105,0.25)',
  methodColors: [
    '#B45309', // amber-700
    '#4338CA', // indigo-700
    '#BE185D', // pink-700
    '#0E7490', // cyan-700
    '#7E22CE', // purple-700
    '#4D7C0F', // lime-700
  ],
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

/** The active theme's chart palette; re-renders the caller when it changes. */
export function useChartPalette(): ChartPalette {
  return CHART_THEME[useResolvedTheme()]
}
