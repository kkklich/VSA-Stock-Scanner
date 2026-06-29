// Left navigation rail. On desktop (lg+) it is a static rail; on smaller
// screens it becomes an off-canvas drawer toggled from the top bar.

import {
  BarChart3,
  LayoutDashboard,
  LineChart,
  LogOut,
  Settings,
  SlidersHorizontal,
  Star,
  TrendingUp,
  X,
} from 'lucide-react'
import type { PageId } from '../App'

const navItems: { id: PageId; label: string; icon: React.ElementType }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'scanner', label: 'Scanner', icon: TrendingUp },
  { id: 'watchlist', label: 'Watchlist', icon: Star },
  { id: 'filters', label: 'Filters', icon: SlidersHorizontal },
  { id: 'charts', label: 'Charts', icon: LineChart },
  { id: 'stats', label: 'Stats', icon: BarChart3 },
]

export function Sidebar({
  active,
  open,
  onNavigate,
  onClose,
}: {
  active: PageId
  open: boolean
  onNavigate: (id: PageId) => void
  onClose: () => void
}) {
  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          aria-hidden
        />
      )}

      <aside
        className={
          'fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-950 transition-transform duration-200 lg:static lg:w-56 lg:translate-x-0 ' +
          (open ? 'translate-x-0' : '-translate-x-full')
        }
      >
        {/* Brand */}
        <div className="flex items-center justify-between px-5 py-5">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-emerald-400 to-emerald-600 text-sm font-bold text-slate-950">
              S
            </div>
            <span className="text-base font-semibold tracking-tight text-slate-100">
              StockPilot
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 lg:hidden"
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        </div>

        {/* Primary nav */}
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {navItems.map(({ id, label, icon: Icon }) => {
            const isActive = active === id
            return (
              <button
                key={id}
                onClick={() => onNavigate(id)}
                className={
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ' +
                  (isActive
                    ? 'bg-slate-800/80 text-slate-100 ring-1 ring-inset ring-slate-700'
                    : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200')
                }
              >
                <Icon
                  className={isActive ? 'text-emerald-400' : ''}
                  size={18}
                  strokeWidth={2}
                />
                {label}
              </button>
            )
          })}
        </nav>

        {/* Bottom utility nav */}
        <div className="space-y-1 border-t border-slate-800 px-3 py-3">
          <button
            onClick={() => onNavigate('settings')}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800/40 hover:text-slate-200"
          >
            <Settings size={18} />
            Settings
          </button>
          <button className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800/40 hover:text-slate-200">
            <LogOut size={18} />
            Logout
          </button>
        </div>
      </aside>
    </>
  )
}
