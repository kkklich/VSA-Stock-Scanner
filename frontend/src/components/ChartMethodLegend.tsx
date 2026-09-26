// On-chart trading-method chooser + legend. One toggle chip per method: its
// marker as it appears on the chart (VSA's arrow; every other method's dot in
// its own colour), the method name, and how many of its signals fall in the
// loaded range. Clicking a chip shows or hides that method's markers. The dot
// colour is how a method is recognised on the candlesticks, so chip and dot
// are always driven by the same value passed in from the page.
//
// Below the chips sits the colour key for the other channel: whether a signal
// is good or bad news. VSA's arrows and every method's label are green
// (positive), red (negative) or grey (a pattern seen, not taken); the key
// paints its words with the same `markerColor` rule the chart uses, so the two
// can never disagree.

import { useTranslation } from 'react-i18next'
import { markerColor, useChartPalette } from '../lib/chartTheme'

export interface ChartMethodLegendItem {
  id: string
  name: string
  /** The marker this method draws: VSA's arrows, or a dot for the others. */
  shape: 'arrow' | 'circle'
  /** Marker colour on the chart (also the chip swatch). */
  color: string
  /** How many of this method's markers fall in the loaded range. */
  count: number
  /** Whether this method's markers are currently shown. */
  selected: boolean
}

/** The chip's picture of a marker: solid when shown, outlined when hidden. */
function MarkerGlyph({
  shape,
  color,
  filled,
}: {
  shape: 'arrow' | 'circle'
  color: string
  filled: boolean
}) {
  const paint = filled
    ? { fill: color }
    : { fill: 'none', stroke: color, strokeWidth: 1.5 }
  return (
    <svg viewBox="0 0 10 10" className="h-2.5 w-2.5 shrink-0" aria-hidden="true">
      {shape === 'arrow' ? (
        <path d="M5 1.2 9 8.8H1Z" strokeLinejoin="round" {...paint} />
      ) : (
        <circle cx="5" cy="5" r="4" {...paint} />
      )}
    </svg>
  )
}

export function ChartMethodLegend({
  items,
  onToggle,
}: {
  items: ChartMethodLegendItem[]
  onToggle: (id: string) => void
}) {
  const { t } = useTranslation()
  const palette = useChartPalette()
  if (items.length === 0) return null

  const key = [
    { id: 'positive', color: markerColor('Bullish', palette) },
    { id: 'negative', color: markerColor('Bearish', palette) },
    { id: 'watch', color: markerColor('Watch', palette) },
  ] as const

  return (
    <div className="mb-2 flex flex-col gap-1.5 px-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {t('chart.methods.legend')}
        </span>
        {items.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onToggle(m.id)}
            aria-pressed={m.selected}
            title={t('chart.methods.toggle', { name: m.name })}
            className={
              'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ' +
              (m.selected
                ? 'border-slate-600 bg-slate-800/80 text-slate-200'
                : 'border-slate-800 bg-slate-900 text-slate-500 hover:bg-slate-800')
            }
          >
            <MarkerGlyph shape={m.shape} color={m.color} filled={m.selected} />
            <span className={m.selected ? '' : 'line-through decoration-slate-600'}>
              {m.name}
            </span>
            <span className="rounded bg-slate-950/60 px-1 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
              {m.count}
            </span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {t('chart.methods.key')}
        </span>
        {key.map((k) => (
          <span
            key={k.id}
            title={t(`chart.methods.${k.id}Hint`)}
            className="font-medium"
            style={{ color: k.color }}
          >
            {t(`chart.methods.${k.id}`)}
          </span>
        ))}
        <span title={t('chart.methods.dotIsMethodHint')} className="text-slate-500">
          · {t('chart.methods.dotIsMethod')}
        </span>
      </div>
    </div>
  )
}
