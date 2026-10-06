// App shell + client-side routing (react-router-dom).
// The Layout renders the persistent sidebar + top bar and an <Outlet> for the
// active route. "/" is the home page (Watchlist). Each stock has its own URL
// at /stock/:ticker so links are shareable and indexable.

import { useState } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { Footer } from './components/Footer'
import { DashboardPage } from './pages/DashboardPage'
import { WatchlistPage } from './pages/WatchlistPage'
import { ChartsPage } from './pages/ChartsPage'
import { ScannerPage } from './pages/ScannerPage'
import { SectorHeatmapPage } from './pages/SectorHeatmapPage'
import { VolumeSurgePage } from './pages/VolumeSurgePage'
import { CapexPage } from './pages/CapexPage'
import { FiltersPage } from './pages/FiltersPage'
import { SettingsPage } from './pages/SettingsPage'
import { SystemPage } from './pages/SystemPage'
import { HelpPage } from './pages/HelpPage'
import { VsaKompendiumPage } from './pages/VsaKompendiumPage'
import { EducationPage } from './pages/EducationPage'
import { EducationArticlePage } from './pages/EducationArticlePage'
import { LegalPage } from './pages/LegalPage'
import { LoginPage } from './pages/LoginPage'
import { usePageSeo } from './lib/seo'

/** Translation key (under `pageTitles`) for the top-bar title of the current path. */
function titleKeyForPath(pathname: string): string {
  if (pathname === '/') return 'pageTitles.dashboard'
  if (pathname.startsWith('/watchlist')) return 'pageTitles.watchlist'
  if (pathname.startsWith('/scanner')) return 'pageTitles.scanner'
  if (pathname.startsWith('/heatmap')) return 'pageTitles.heatmap'
  if (pathname.startsWith('/volume-surge')) return 'pageTitles.volumeSurge'
  if (pathname.startsWith('/capex')) return 'pageTitles.investment'
  if (pathname.startsWith('/stock/')) return 'pageTitles.stock'
  if (pathname.startsWith('/filters')) return 'pageTitles.filters'
  if (pathname.startsWith('/settings')) return 'pageTitles.settings'
  if (pathname.startsWith('/system')) return 'pageTitles.system'
  if (pathname.startsWith('/help')) return 'pageTitles.help'
  if (pathname.startsWith('/education')) return 'pageTitles.education'
  if (pathname.startsWith('/legal')) return 'pageTitles.legal'
  if (pathname.startsWith('/login')) return 'pageTitles.login'
  return 'pageTitles.app'
}

function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const { t } = useTranslation()

  // Keep the document title + meta description in sync with the active route.
  usePageSeo(pathname)

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={t(titleKeyForPath(pathname))}
          onMenuClick={() => setMenuOpen(true)}
        />

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
          {/* Legal notice + publisher contact, on every page. */}
          <Footer />
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
        <Route path="settings" element={<SettingsPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="help" element={<HelpPage />} />
        {/* Education section (agent/ROADMAP.md #32). The Kompendium used to
            live at /vsa-kompendium; that address keeps working as a redirect. */}
        <Route path="education" element={<EducationPage />} />
        <Route path="education/vsa-kompendium" element={<VsaKompendiumPage />} />
        <Route path="education/:slug" element={<EducationArticlePage />} />
        <Route path="education/*" element={<Navigate to="/education" replace />} />
        <Route
          path="vsa-kompendium"
          element={<Navigate to="/education/vsa-kompendium" replace />}
        />
        <Route path="legal" element={<LegalPage />} />
        {/* Sign in / create an account. Optional: every other page works
            signed out, so this is a normal page, not a gate. */}
        <Route path="login" element={<LoginPage />} />
        {/* Unknown paths fall back to the home page */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
