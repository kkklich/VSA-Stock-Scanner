// "Columns" dropdown for the ranking / screener table: a checklist that toggles
// which columns are shown. The identity column is locked on; everything else
// can be hidden. Selection is owned by the page (persisted in localStorage), so
// this component is purely presentational.

import { useState } from 'react'
import { Columns3, RotateCcw } from 'lucide-react'
import {
  RANKING_COLUMNS,
  isColumnVisible,
  type ColumnVisibility,
  type RankingColumnId,
} from '../lib/rankingColumns'

export function ColumnPicker({
  value,
  onToggle,
  onReset,
  customized,
  visibleCount,
}: {
  value: ColumnVisibility
  onToggle: (id: RankingColumnId) => void
  onReset: () => void
  /** Whether the current selection differs from the defaults. */
  customized: boolean
  visibleCount: number
}) {
  const [open, setOpen] = useState(false)

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
        title="Choose which columns to show"
      >
        <Columns3 size={14} />
        <span className="hidden sm:inline">Columns</span>
        <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
          {visibleCount}
        </span>
      </button>

      {open && (
        <>
          {/* Click-away backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-64 rounded-lg border border-slate-800 bg-slate-900 p-2 shadow-xl">
            <div className="flex items-center justify-between px-2 py-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Show columns
              </span>
              <button
                type="button"
                onClick={onReset}
                disabled={!customized}
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                title="Restore the default columns"
              >
                <RotateCcw size={11} /> Reset
              </button>
            </div>

            <div className="max-h-72 overflow-y-auto">
              {RANKING_COLUMNS.map((col) => {
                const checked = isColumnVisible(col, value)
                return (
                  <label
                    key={col.id}
                    className={
                      'flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors ' +
                      (col.required
                        ? 'cursor-default text-slate-500'
                        : 'text-slate-200 hover:bg-slate-800')
                    }
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={col.required}
                      onChange={() => onToggle(col.id)}
                      className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-950 text-emerald-500 accent-emerald-500 focus:ring-0 disabled:opacity-60"
                    />
                    <span className="flex-1">{col.menuLabel ?? col.label}</span>
                    {col.required && (
                      <span className="text-[10px] uppercase tracking-wide text-slate-600">
                        locked
                      </span>
                    )}
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
