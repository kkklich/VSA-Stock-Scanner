// Slim top bar: hamburger (mobile) + page title on the left; market status,
// last EOD sync, and a user avatar on the right (DOCUMENTATION.md §3).

import { Menu } from 'lucide-react'
import { lastSyncLabel } from '../data/mockData'

export function TopBar({
  title,
  onMenuClick,
}: {
  title: string
  onMenuClick: () => void
}) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/80 px-4 backdrop-blur sm:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <button
          onClick={onMenuClick}
          className="-ml-1 rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 lg:hidden"
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>
        <h1 className="truncate text-sm font-semibold text-slate-200">
          {title}
        </h1>
      </div>

      <div className="flex items-center gap-3 text-xs sm:gap-5">
        <span className="hidden text-slate-500 md:inline">
          Last sync: <span className="text-slate-300">{lastSyncLabel}</span>
        </span>
        <span className="flex items-center gap-1.5 text-slate-400">
          <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/70" />
          <span className="hidden sm:inline">Market:</span>
          <span className="font-semibold text-emerald-400">OPEN</span>
        </span>
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-800 text-[11px] font-semibold text-slate-300 ring-1 ring-slate-700">
          AM
        </div>
      </div>
    </header>
  )
}
