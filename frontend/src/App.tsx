// App shell + client-side routing (react-router-dom).
// The Layout renders the persistent sidebar + top bar and an <Outlet> for the
// active route. "/" is the home page (Watchlist). Each stock has its own URL
// at /stock/:ticker so links are shareable and indexable.

import { useState } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { DashboardPage } from './pages/DashboardPage'
import { WatchlistPage } from './pages/WatchlistPage'
import { ChartsPage } from './pages/ChartsPage'
import { ScannerPage } from './pages/ScannerPage'
import { SectorHeatmapPage } from './pages/SectorHeatmapPage'
import { VolumeSurgePage } from './pages/VolumeSurgePage'
import { CapexPage } from './pages/CapexPage'
import { FiltersPage } from './pages/FiltersPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { HelpPage } from './pages/HelpPage'
import { usePageSeo } from './lib/seo'

/** Human-readable top-bar title for the current path. */
function titleForPath(pathname: string): string {
  if (pathname === '/') return 'Dashboard'
  if (pathname.startsWith('/watchlist')) return 'Watchlist'
  if (pathname.startsWith('/scanner')) return 'VSA Scanner — GPW'
  if (pathname.startsWith('/heatmap')) return 'Sector Heatmap'
  if (pathname.startsWith('/volume-surge')) return 'Volume Surge'
  if (pathname.startsWith('/capex')) return 'Investment Spending'
  if (pathname.startsWith('/stock/')) return 'Stock Detail'
  if (pathname.startsWith('/filters')) return 'Filters'
  if (pathname.startsWith('/settings')) return 'Settings'
  if (pathname.startsWith('/help')) return 'How to use StockPilot'
  return 'StockPilot'
}

function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()

  // Keep the document title + meta description in sync with the active route.
  usePageSeo(pathname)

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={titleForPath(pathname)}
          onMenuClick={() => setMenuOpen(true)}
        />

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Home / main page */}
        <Route index element={<DashboardPage />} />
        {/* /dashboard is an alias for the home page */}
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route path="scanner" element={<ScannerPage />} />
        <Route path="heatmap" element={<SectorHeatmapPage />} />
        <Route path="volume-surge" element={<VolumeSurgePage />} />
        <Route path="capex" element={<CapexPage />} />
        <Route path="stock/:ticker" element={<ChartsPage />} />
        <Route path="filters" element={<FiltersPage />} />
        <Route path="settings" element={<PlaceholderPage title="Settings" />} />
        <Route path="help" element={<HelpPage />} />
        {/* Unknown paths fall back to the home page */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
