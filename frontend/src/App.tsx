// App shell: persistent sidebar + top bar, with a lightweight state-based
// router switching between the primary screens. (A real router can drop in
// later; this keeps the mock-first build self-contained.)

import { useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { WatchlistPage } from './pages/WatchlistPage'
import { ChartsPage } from './pages/ChartsPage'
import { ScannerPage } from './pages/ScannerPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

export type PageId =
  | 'dashboard'
  | 'scanner'
  | 'watchlist'
  | 'filters'
  | 'charts'
  | 'stats'
  | 'settings'

const titles: Record<PageId, string> = {
  dashboard: 'Dashboard',
  scanner: 'VSA Scanner — GPW',
  watchlist: 'Watchlist',
  filters: 'Filters',
  charts: 'Stock Detail',
  stats: 'Statistics',
  settings: 'Settings',
}

export default function App() {
  const [page, setPage] = useState<PageId>('watchlist')
  const [menuOpen, setMenuOpen] = useState(false)

  const navigate = (id: PageId) => {
    setPage(id)
    setMenuOpen(false) // close the mobile drawer after picking a destination
  }

  // Clicking a ticker in the watchlist drills into the chart/detail view.
  const openTicker = (_ticker: string) => navigate('charts')

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100">
      <Sidebar
        active={page}
        open={menuOpen}
        onNavigate={navigate}
        onClose={() => setMenuOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={titles[page]} onMenuClick={() => setMenuOpen(true)} />

        <main className="min-h-0 flex-1 overflow-y-auto">
          {page === 'watchlist' && <WatchlistPage onSelect={openTicker} />}
          {page === 'charts' && <ChartsPage />}
          {page === 'scanner' && <ScannerPage />}
          {page === 'dashboard' && <PlaceholderPage title="Dashboard" />}
          {page === 'filters' && <PlaceholderPage title="Filters" />}
          {page === 'stats' && <PlaceholderPage title="Statistics" />}
          {page === 'settings' && <PlaceholderPage title="Settings" />}
        </main>
      </div>
    </div>
  )
}
