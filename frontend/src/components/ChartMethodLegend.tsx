// On-chart trading-method chooser + legend. One toggle chip per method: a
// colour swatch matching that method's markers on the chart, the method name,
// and how many of its signals fall in the loaded range. Clicking a chip shows
// or hides that method's markers. The colour is the legend — it's the only way
// to tell the layers apart on the candlesticks — so chip and marker colour are
// always driven by the same value passed in from the page.

import { useTranslation } from 'react-i18next'

export interface ChartMethodLegendItem {
  id: string
  name: string
  /** Marker colour on the chart (also the chip swatch). */
  color: string
  /** How many of this method's markers fall in the loaded range. */
  count: number
  /** Whether this method's markers are currently shown. */
  selected: boolean
}

export function ChartMethodLegend({
  items,
  onToggle,
}: {
  items: ChartMethodLegendItem[]
  onToggle: (id: string) => void
}) {
  const { t } = useTranslation()
  if (items.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 px-1">
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
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{
              backgroundColor: m.selected ? m.color : 'transparent',
              boxShadow: m.selected ? 'none' : `inset 0 0 0 1.5px ${m.color}`,
            }}
          />
          <span className={m.selected ? '' : 'line-through decoration-slate-600'}>
            {m.name}
          </span>
          <span className="rounded bg-slate-950/60 px-1 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
            {m.count}
          </span>
        </button>
      ))}
    </div>
  )
}
