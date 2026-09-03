// "Methods" multi-select dropdown for the dashboard. Lists every available
// trading method (VSA + the pluggable ones) with its plain-language
// description and a link to its source, and lets the user choose which ones
// appear as columns. Selection is owned by the page (persisted in
// localStorage); this component is presentational.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Layers, RotateCcw } from 'lucide-react'
import type { ApiTradingMethod } from '../api/stocksApi'

export function MethodPicker({
  methods,
  selected,
  onToggle,
  onReset,
  customized,
}: {
  methods: ApiTradingMethod[]
  /** Currently selected method ids. */
  selected: string[]
  onToggle: (id: string) => void
  onReset: () => void
  /** Whether the selection differs from the default (all methods). */
  customized: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const selectedSet = new Set(selected)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={
          'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
          (customized
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
            : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800')
        }
        aria-haspopup="true"
        aria-expanded={open}
        title={t('methods.title')}
      >
        <Layers size={14} />
        <span className="hidden sm:inline">{t('methods.button')}</span>
        <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
          {selected.length}
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-800 bg-slate-900 p-2 shadow-xl">
            <div className="flex items-center justify-between px-2 py-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {t('methods.heading')}
              </span>
              <button
                type="button"
                onClick={onReset}
                disabled={!customized}
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                title={t('methods.showAll')}
              >
                <RotateCcw size={11} /> {t('methods.all')}
              </button>
            </div>

            <div className="max-h-96 overflow-y-auto">
              {methods.map((m) => {
                const checked = selectedSet.has(m.id)
                return (
                  <label
                    key={m.id}
                    className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-2 text-sm transition-colors hover:bg-slate-800"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(m.id)}
                      className="mt-0.5 h-3.5 w-3.5 rounded border-slate-600 bg-slate-950 text-emerald-500 accent-emerald-500 focus:ring-0"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="font-medium text-slate-200">{m.name}</span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">
                        {m.description}
                      </span>
                      <span className="mt-1 block text-[11px] text-slate-600">
                        {t('methods.source')}{' '}
                        {m.sourceUrl ? (
                          <a
                            href={m.sourceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-slate-400 underline decoration-slate-700 underline-offset-2 hover:text-slate-200"
                          >
                            {m.source}
                          </a>
                        ) : (
                          <span className="text-slate-500">{m.source}</span>
                        )}
                      </span>
                    </span>
                  </label>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
