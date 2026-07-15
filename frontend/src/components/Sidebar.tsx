// Left navigation rail. On desktop (lg+) it is a static rail; on smaller
// screens it becomes an off-canvas drawer toggled from the top bar.
// Navigation uses react-router <Link>s; the active item is derived from the
// current path.

import {
  Activity,
  BookOpen,
  Filter,
  LayoutDashboard,
  LayoutGrid,
  LineChart,
  Settings,
  Star,
  TrendingUp,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

type NavItem = {
  to: string
  label: string
  icon: React.ElementType
  /** Returns true when this item should appear active for the given path. */
  match: (pathname: string) => boolean
}

const navItems: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, match: (p) => p === '/' },
  {
    to: '/watchlist',
    label: 'Watchlist',
    icon: Star,
    match: (p) => p.startsWith('/watchlist'),
  },
  {
    to: '/scanner',
    label: 'Scanner',
    icon: TrendingUp,
    match: (p) => p.startsWith('/scanner'),
  },
  {
    to: '/heatmap',
    label: 'Sector heatmap',
    icon: LayoutGrid,
    match: (p) => p.startsWith('/heatmap'),
  },
  {
    to: '/volume-surge',
    label: 'Volume surge',
    icon: Activity,
    match: (p) => p.startsWith('/volume-surge'),
  },
  {
    to: '/filters',
    label: 'Filters',
    icon: Filter,
    match: (p) => p.startsWith('/filters'),
  },
  {
    to: '/stock/kgh',
    label: 'Charts',
    icon: LineChart,
    match: (p) => p.startsWith('/stock'),
  },
]

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { pathname } = useLocation()

  const linkClass = (isActive: boolean) =>
    'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ' +
    (isActive
      ? 'bg-slate-800/80 text-slate-100 ring-1 ring-inset ring-slate-700'
      : 'text-slate-400 hover:bg-slate-800/40 hover:text-slate-200')

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
          <Link to="/" onClick={onClose} className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-emerald-400 to-emerald-600 text-sm font-bold text-slate-950">
              S
            </div>
            <span className="text-base font-semibold tracking-tight text-slate-100">
              StockPilot
            </span>
          </Link>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 lg:hidden"
            aria-label="Close menu"
          >
            <span className="text-xl leading-none">×</span>
          </button>
        </div>

        {/* Primary nav */}
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {navItems.map(({ to, label, icon: Icon, match }) => {
            const isActive = match(pathname)
            return (
              <Link
                key={to}
                to={to}
                onClick={onClose}
                className={linkClass(isActive)}
              >
                <Icon
                  className={isActive ? 'text-emerald-400' : ''}
                  size={18}
                  strokeWidth={2}
                />
                {label}
              </Link>
            )
          })}
        </nav>

        {/* Bottom utility nav */}
        <div className="space-y-1 border-t border-slate-800 px-3 py-3">
          <Link
            to="/help"
            onClick={onClose}
            className={linkClass(pathname.startsWith('/help'))}
          >
            <BookOpen size={18} />
            Help
          </Link>
          <Link
            to="/settings"
            onClick={onClose}
            className={linkClass(pathname.startsWith('/settings'))}
          >
            <Settings size={18} />
            Settings
          </Link>
        </div>
      </aside>
    </>
  )
}
