// "Columns" dropdown for the ranking tables: a checklist that toggles which
// columns are shown AND arrow buttons that move a column left or right in the
// table. The identity column is locked on and pinned first; everything else can
// be hidden or reordered, on the wide tables and in the phone/tablet card lists
// alike. Both halves of the choice are owned by the page (persisted in
// localStorage and shared by the Dashboard, Watchlist and Filters), so this
// component is purely presentational. The panel positions itself with
// `useDropdownPosition`, which clamps it inside the viewport — on a phone it
// lands on screen rather than hanging off the left edge.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, Columns3, RotateCcw } from 'lucide-react'
import { useDropdownPosition } from '../hooks/useDropdownPosition'
import {
  canMoveColumn,
  columnMenuLabel,
  isColumnVisible,
  orderedColumns,
  type ColumnOrder,
  type ColumnVisibility,
  type RankingColumnId,
} from '../lib/rankingColumns'

/** Width the panel gets whenever the screen is wide enough for it. */
const PANEL_WIDTH = 280

/** One reorder arrow; disabled at the ends of the list. */
function MoveButton({
  dir,
  disabled,
  label,
  onClick,
}: {
  dir: 'up' | 'down'
  disabled: boolean
  label: string
  onClick: () => void
}) {
  const Icon = dir === 'up' ? ChevronUp : ChevronDown
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded p-2 text-slate-500 transition-colors hover:bg-slate-700 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-25 disabled:hover:bg-transparent"
    >
      <Icon size={14} />
    </button>
  )
}

export function ColumnPicker({
  value,
  order,
  onToggle,
  onMove,
  onReset,
  customized,
  visibleCount,
}: {
  value: ColumnVisibility
  /** Full column order (hidden columns included). */
  order: ColumnOrder
  onToggle: (id: RankingColumnId) => void
  /** Move a column one place earlier (-1) or later (+1) in the table. */
  onMove: (id: RankingColumnId, delta: -1 | 1) => void
  onReset: () => void
  /** Whether the current selection or order differs from the defaults. */
  customized: boolean
  visibleCount: number
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { buttonRef, style: panelStyle } = useDropdownPosition(open, PANEL_WIDTH)

  // The list is shown in the user's own order, so a moved row lands exactly
  // where the table will show it.
  const columns = orderedColumns(order)

  return (
    <div className="relative">
      <button
        type="button"
        ref={buttonRef}
        onClick={() => setOpen((v) => !v)}
        className={
          'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
          (customized
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
            : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800')
        }
        aria-haspopup="true"
        aria-expanded={open}
        title={t('columns.tooltip')}
      >
        <Columns3 size={14} />
        <span className="hidden sm:inline">{t('columns.button')}</span>
        <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
          {visibleCount}
        </span>
      </button>

      {open && (
        <>
          {/* Click-away backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          {panelStyle && (
            <div
              style={panelStyle}
              className="z-20 flex flex-col rounded-lg border border-slate-800 bg-slate-900 p-2 shadow-xl"
            >
              <div className="flex items-center justify-between px-2 py-1">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {t('columns.heading')}
                </span>
                <button
                  type="button"
                  onClick={onReset}
                  disabled={!customized}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                  title={t('columns.resetTooltip')}
                >
                  <RotateCcw size={11} /> {t('common.reset')}
                </button>
              </div>
              <p className="px-2 pb-1.5 text-[11px] leading-snug text-slate-600">
                {t('columns.reorderHint')}
              </p>

              <div className="min-h-0 flex-1 overflow-y-auto">
                {columns.map((col) => {
                  const checked = isColumnVisible(col, value)
                  // Greyed out exactly when the move would change nothing —
                  // at the ends of the list, or against the pinned column.
                  const canMoveUp = canMoveColumn(order, col.id, -1, value)
                  const canMoveDown = canMoveColumn(order, col.id, 1, value)
                  return (
                    <div
                      key={col.id}
                      className={
                        'flex items-center gap-1 rounded-md pr-1 transition-colors ' +
                        (col.required ? '' : 'hover:bg-slate-800')
                      }
                    >
                      <label
                        className={
                          // Roomy rows: this list is tapped on a phone as often
                          // as it is clicked on a desktop.
                          'flex min-w-0 flex-1 items-center gap-2.5 px-2 py-2 text-sm ' +
                          (col.required
                            ? 'cursor-default text-slate-500'
                            : 'cursor-pointer text-slate-200')
                        }
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={col.required}
                          onChange={() => onToggle(col.id)}
                          className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-950 text-emerald-500 accent-emerald-500 focus:ring-0 disabled:opacity-60"
                        />
                        <span className="min-w-0 flex-1 truncate">
                          {columnMenuLabel(col, t)}
                        </span>
                      </label>

                      {col.required ? (
                        <span className="shrink-0 pr-1 text-[10px] uppercase tracking-wide text-slate-600">
                          {t('columns.locked')}
                        </span>
                      ) : (
                        <span className="flex shrink-0 items-center">
                          <MoveButton
                            dir="up"
                            disabled={!canMoveUp}
                            label={t('columns.moveUp', {
                              column: columnMenuLabel(col, t),
                            })}
                            onClick={() => onMove(col.id, -1)}
                          />
                          <MoveButton
                            dir="down"
                            disabled={!canMoveDown}
                            label={t('columns.moveDown', {
                              column: columnMenuLabel(col, t),
                            })}
                            onClick={() => onMove(col.id, 1)}
                          />
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
