// The sort control every list page shows in its toolbar — on ALL screen sizes.
//
// It started as the phone/tablet stand-in for the column headers the card
// layout does not have. It is shown on the desktop too because multi-column
// sorting was otherwise invisible there: the table can be sorted by one column
// and then by another (see `lib/sorting.ts`), but the only way in was a
// shift-click on a header, a gesture nothing on screen advertises — and
// because a tie-break often reorders nothing visible, a user who never found
// the gesture, and a user who found it and added a level to a column with no
// ties, both saw exactly the same thing: no change at all.
//
// So the panel states the ordering outright, in two halves: the active sort
// levels at the top, numbered, each with its own direction switch and a remove
// button, and below them the remaining columns, where a click appends a
// "then by" level. Clicking an active level's name makes it the only sort
// again — the one-click way back to a simple ordering.
//
// The headers still work (and shift-click still adds a level) for anyone who
// prefers them; this is the same state, shown.
//
// Presentational: the page owns the levels and passes the same `onSort`
// handler its table headers use, so both layouts drive one state.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowDownUp, ArrowUp, Plus, X } from 'lucide-react'
import { useDropdownPosition } from '../hooks/useDropdownPosition'
import { MAX_SORT_LEVELS, type SortDir, type SortLevel } from '../lib/sorting'

/** Width the panel gets whenever the screen is wide enough for it. */
const PANEL_WIDTH = 260

export type SortOption<T extends string> = { key: T; label: string }

export function SortMenu<T extends string>({
  options,
  sort,
  onSort,
  onSortDirChange,
  onRemoveLevel,
  className = '',
}: {
  options: SortOption<T>[]
  /** The whole sort, outermost level first. */
  sort: SortLevel<T>[]
  /**
   * Same handler the table headers use. `additive` is the touch equivalent of
   * shift-click: append a "then by" level instead of replacing the sort.
   */
  onSort: (col: T, additive: boolean) => void
  /** Set one level's direction explicitly. */
  onSortDirChange: (col: T, dir: SortDir) => void
  /** Drop one level (never called for the last remaining one). */
  onRemoveLevel: (col: T) => void
  /** Extra classes on the wrapper (the pages use it for `lg:hidden`). */
  className?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { buttonRef, style: panelStyle } = useDropdownPosition(open, PANEL_WIDTH)

  const labelOf = (key: T) => options.find((o) => o.key === key)?.label ?? key
  const primary = sort[0]
  const DirIcon = primary?.dir === 'asc' ? ArrowUp : ArrowDown
  const sorted = new Set(sort.map((l) => l.key))
  const rest = options.filter((o) => !sorted.has(o.key))
  const canAdd = sort.length < MAX_SORT_LEVELS

  return (
    <div className={'relative ' + className}>
      <button
        type="button"
        ref={buttonRef}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        title={t('common.sortHeading')}
        className="inline-flex max-w-[12rem] items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800"
      >
        <ArrowDownUp size={14} className="shrink-0" />
        <span className="truncate">
          {primary ? labelOf(primary.key) : t('common.sort')}
        </span>
        <DirIcon size={12} className="shrink-0 text-emerald-400" />
        {sort.length > 1 && (
          <span className="shrink-0 rounded bg-emerald-500/15 px-1 text-[10px] font-semibold text-emerald-300">
            +{sort.length - 1}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          {panelStyle && (
            <div
              style={panelStyle}
              role="menu"
              className="z-20 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900 p-2 shadow-xl"
            >
              <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {t('common.sortHeading')}
              </p>

              {/* The active levels, outermost first. */}
              <div className="flex flex-col gap-1.5">
                {sort.map((level, i) => (
                  <div key={level.key} className="flex items-center gap-1">
                    <span
                      aria-hidden="true"
                      className="w-4 shrink-0 text-center text-[10px] font-semibold text-slate-500"
                    >
                      {sort.length > 1 ? i + 1 : ''}
                    </span>
                    <button
                      type="button"
                      role="menuitemradio"
                      aria-checked={i === 0}
                      // Tapping an active level's name is the way back to a
                      // plain one-column sort (what a desktop plain click does).
                      onClick={() => onSort(level.key, false)}
                      className="flex min-w-0 flex-1 items-center rounded-md bg-emerald-500/15 px-2 py-2 text-left text-sm text-emerald-300"
                    >
                      <span className="truncate">{labelOf(level.key)}</span>
                    </button>
                    {(['asc', 'desc'] as const).map((dir) => {
                      const isActive = level.dir === dir
                      const Icon = dir === 'asc' ? ArrowUp : ArrowDown
                      return (
                        <button
                          key={dir}
                          type="button"
                          aria-pressed={isActive}
                          aria-label={t(
                            dir === 'asc'
                              ? 'common.sortLevelAsc'
                              : 'common.sortLevelDesc',
                            { label: labelOf(level.key) },
                          )}
                          onClick={() => onSortDirChange(level.key, dir)}
                          className={
                            'inline-flex shrink-0 items-center justify-center rounded-md p-1.5 transition-colors ' +
                            (isActive
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : 'bg-slate-800 text-slate-400 hover:bg-slate-700')
                          }
                        >
                          <Icon size={12} />
                        </button>
                      )
                    })}
                    <button
                      type="button"
                      disabled={sort.length === 1}
                      aria-label={t('common.sortRemoveLevel', {
                        label: labelOf(level.key),
                      })}
                      onClick={() => onRemoveLevel(level.key)}
                      className="inline-flex shrink-0 items-center justify-center rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>

              {/* "Then by": the columns not yet part of the sort. */}
              {rest.length > 0 && (
                <>
                  <p className="mt-2 border-t border-slate-800 px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    {canAdd
                      ? t('common.sortThenBy')
                      : t('common.sortReplaceLast', { max: MAX_SORT_LEVELS })}
                  </p>
                  <div className="flex flex-col gap-0.5">
                    {rest.map((o) => (
                      <button
                        key={o.key}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          onSort(o.key, true)
                          setOpen(false)
                        }}
                        className="flex items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm text-slate-300 transition-colors hover:bg-slate-800"
                      >
                        <span className="truncate">{o.label}</span>
                        <Plus size={14} className="shrink-0 text-slate-500" />
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
