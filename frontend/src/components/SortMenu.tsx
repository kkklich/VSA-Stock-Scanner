// Sort control for the card lists shown below `lg`.
//
// The wide-screen tables sort by tapping a column header (`SortHeader`), but
// the phone/tablet layout swaps those tables for stacked cards — which have no
// headers, so on a small screen there was no way to change the ordering at all.
// This is that missing control: a toolbar dropdown listing the same columns the
// desktop table can sort by, plus an explicit ascending/descending switch (a
// tap target is a poor place to hide "tap again to flip the direction").
//
// Presentational: the page owns `sortBy` / `sortDir` and passes the same
// `onSort` handler its table headers use, so both layouts drive one state.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowDownUp, ArrowUp, Check } from 'lucide-react'
import { useDropdownPosition } from '../hooks/useDropdownPosition'

/** Width the panel gets whenever the screen is wide enough for it. */
const PANEL_WIDTH = 240

export type SortOption<T extends string> = { key: T; label: string }

export function SortMenu<T extends string>({
  options,
  sortBy,
  sortDir,
  onSort,
  onSortDirChange,
  className = '',
}: {
  options: SortOption<T>[]
  sortBy: T
  sortDir: 'asc' | 'desc'
  /** Same handler the table headers use: selects a column (or flips it). */
  onSort: (col: T) => void
  onSortDirChange: (dir: 'asc' | 'desc') => void
  /** Extra classes on the wrapper (the pages use it for `lg:hidden`). */
  className?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { buttonRef, style: panelStyle } = useDropdownPosition(open, PANEL_WIDTH)

  const active = options.find((o) => o.key === sortBy)
  const DirIcon = sortDir === 'asc' ? ArrowUp : ArrowDown

  const pick = (key: T) => {
    onSort(key)
    // Choosing a different column closes the menu; tapping the active one
    // flips the direction, and the user may want to flip it straight back.
    if (key !== sortBy) setOpen(false)
  }

  return (
    <div className={'relative ' + className}>
      <button
        type="button"
        ref={buttonRef}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        title={t('common.sortHeading')}
        className="inline-flex max-w-[11rem] items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800"
      >
        <ArrowDownUp size={14} className="shrink-0" />
        <span className="truncate">{active?.label ?? t('common.sort')}</span>
        <DirIcon size={12} className="shrink-0 text-emerald-400" />
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
              <div className="flex flex-col gap-0.5">
                {options.map((o) => {
                  const isActive = o.key === sortBy
                  return (
                    <button
                      key={o.key}
                      type="button"
                      role="menuitemradio"
                      aria-checked={isActive}
                      onClick={() => pick(o.key)}
                      className={
                        'flex items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors ' +
                        (isActive
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'text-slate-300 hover:bg-slate-800')
                      }
                    >
                      {o.label}
                      {isActive && <Check size={14} className="shrink-0" />}
                    </button>
                  )
                })}
              </div>

              <div className="mt-2 grid grid-cols-2 gap-1 border-t border-slate-800 pt-2">
                {(['asc', 'desc'] as const).map((dir) => {
                  const isActive = sortDir === dir
                  const Icon = dir === 'asc' ? ArrowUp : ArrowDown
                  return (
                    <button
                      key={dir}
                      type="button"
                      aria-pressed={isActive}
                      onClick={() => onSortDirChange(dir)}
                      className={
                        'inline-flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs transition-colors ' +
                        (isActive
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
                      }
                    >
                      <Icon size={12} />
                      {dir === 'asc' ? t('common.sortAsc') : t('common.sortDesc')}
                    </button>
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
