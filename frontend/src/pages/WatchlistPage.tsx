// Watchlist / ranking table page — the app's home page ("/").
// Backed by GET /api/stocks/ranking via the useRanking hook.
// Favorites (stars) persist in localStorage, sort to the top, and can be
// filtered to "favorites only". Clicking a row opens /stock/:ticker.
//
// Header actions (all functional):
//   Filter    — dropdown to filter by VSA rating / signal
//   Refresh   — run the backend refresh pipeline (Yahoo → ratings → DB), then refetch
//   Export    — download the current view as CSV

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Download,
  Loader2,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Star,
} from 'lucide-react'
import { useRanking, type RankingParams } from '../hooks/useRanking'
import {
  fetchRanking,
  type RankingSortKey,
  type SortDir,
} from '../api/stocksApi'
import type { SignalVerdict, StockRankingItem } from '../types'
import { loadFavorites, saveFavorites } from '../lib/favorites'
import { settingsQueryValue } from '../lib/vsaSettings'
import { RATING_OPTIONS, SIGNAL_OPTIONS } from '../lib/filterOptions'
import { Pagination } from '../components/ui'
import { RefreshButton } from '../components/RefreshButton'
import { ColumnPicker } from '../components/ColumnPicker'
import { RankingCardList, RankingTable } from '../components/RankingTable'
import { SortMenu } from '../components/SortMenu'
import { useDropdownPosition } from '../hooks/useDropdownPosition'
import { sortOptionsFrom, useRankingColumns } from '../hooks/useRankingColumns'
import { initialSortDir, tableMinWidth } from '../lib/rankingColumns'

/** Full-page loading skeleton for the ranking table. */
function LoadingSkeleton() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-slate-400">
      <Loader2 size={36} className="animate-spin text-emerald-500" />
      <div className="text-center">
        <p className="font-medium text-slate-300">Computing VSA rankings…</p>
        <p className="mt-1 text-sm text-slate-500">
          Fetching GPW data from Yahoo Finance — the first load can take a few
          minutes. Subsequent loads are instant.
        </p>
      </div>
    </div>
  )
}

/** Error banner shown when the API is unreachable or returns an error. */
function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mx-4 mt-4 flex items-center justify-between gap-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm sm:mx-6">
      <span className="text-rose-300">
        <span className="font-semibold">Backend error:</span> {message}
      </span>
      <button
        onClick={onRetry}
        className="flex shrink-0 items-center gap-1.5 rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500"
      >
        <RefreshCw size={13} /> Retry
      </button>
    </div>
  )
}

const PAGE_SIZE = 50

export function WatchlistPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()

  const [query, setQuery] = useState('')
  // Debounced search text — avoids firing a request on every keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)
  const { buttonRef: filterButtonRef, style: filterStyle } =
    useDropdownPosition(filterOpen, 240)
  const [minRating, setMinRating] = useState(0)
  const [signalFilter, setSignalFilter] = useState<SignalVerdict | 'all'>('all')
  const [currentPage, setCurrentPage] = useState(1)
  const [exporting, setExporting] = useState(false)

  // Sort state — every column header drives these, sent to the backend.
  const [sortBy, setSortBy] = useState<RankingSortKey>('currentRating')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Starred tickers, persisted across sessions in localStorage.
  const [stars, setStars] = useState<Record<string, boolean>>(loadFavorites)

  useEffect(() => {
    saveFavorites(stars)
  }, [stars])

  // Debounce the search box (300 ms) before it becomes a query parameter.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(query.trim()), 300)
    return () => clearTimeout(timer)
  }, [query])

  const toggleStar = (ticker: string) =>
    setStars((p) => ({ ...p, [ticker]: !p[ticker] }))

  const openTicker = (ticker: string) => navigate(`/stock/${ticker.toLowerCase()}`)

  // Tickers currently starred — the allow-list sent to the backend when the
  // "favorites only" (or edit) view is active.
  const favTickers = useMemo(
    () => Object.keys(stars).filter((t) => stars[t]),
    [stars],
  )
  const favCount = favTickers.length

  const filtersActive = minRating > 0 || signalFilter !== 'all'

  // Everything below is computed by the backend — this hook just requests the
  // right page with the right sort/filter/search.
  const rankingParams = useMemo<RankingParams>(
    () => ({
      page: currentPage,
      pageSize: PAGE_SIZE,
      sortBy,
      sortDir,
      q: debouncedSearch || undefined,
      minRating: minRating || undefined,
      signal: signalFilter,
      tickers: favoritesOnly ? favTickers : undefined,
    }),
    [
      currentPage,
      sortBy,
      sortDir,
      debouncedSearch,
      minRating,
      signalFilter,
      favoritesOnly,
      favTickers,
    ],
  )

  const { data, total, loading, error, refetch } = useRanking(rankingParams)

  // Overlay the client-only "starred" flag onto the current page of results.
  const rows = useMemo<StockRankingItem[]>(
    () =>
      (data ?? []).map((item) => ({
        ...item,
        starred: stars[item.ticker] ?? false,
      })),
    [data, stars],
  )

  // Reset to the first page whenever the query shape changes.
  useEffect(() => {
    setCurrentPage(1)
  }, [debouncedSearch, favoritesOnly, minRating, signalFilter, sortBy, sortDir])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const onSort = (col: RankingSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      // Text columns read best ascending; metrics best descending.
      setSortDir(initialSortDir(col))
    }
  }

  // Which columns to show — shared with the Dashboard and Filters pages, and
  // used by both the wide table and the card list below `lg`.
  const columns = useRankingColumns()
  const sortOptions = useMemo(
    () => sortOptionsFrom(columns.renderColumns, sortBy, t),
    [columns.renderColumns, sortBy, t],
  )

  const clearFilters = () => {
    setMinRating(0)
    setSignalFilter('all')
  }

  /** Download the current (filtered + sorted) view as a CSV file. Fetches all
   *  matching rows from the backend, not just the visible page. */
  const handleExport = async () => {
    setExporting(true)
    try {
      // The backend caps pageSize at 500 — keep fetching pages until every
      // matching row is in, so large exports aren't silently truncated.
      const baseQuery = {
        pageSize: 500,
        sortBy,
        sortDir,
        q: debouncedSearch || undefined,
        minRating: minRating || undefined,
        signal: signalFilter,
        tickers: favoritesOnly ? favTickers : undefined,
        settings: settingsQueryValue(),
      }
      const first = await fetchRanking({ ...baseQuery, page: 1 })
      const items = [...first.items]
      let page = 2
      while (items.length < first.total) {
        const next = await fetchRanking({ ...baseQuery, page })
        if (next.items.length === 0) break // safety: never loop forever
        items.push(...next.items)
        page += 1
      }
      const header = [
        'Symbol',
        'Name',
        'Last Price (PLN)',
        'Change %',
        'VSA Rating',
        'Last Signal',
        'Days Since Signal',
        'Favorite',
      ]
      // Quote-escape, and prefix leading =, +, -, @ with ' so spreadsheet
      // apps don't execute cell values as formulas.
      const esc = (v: string) =>
        `"${(/^[=+\-@]/.test(v) ? `'${v}` : v).replace(/"/g, '""')}"`
      const lines = items.map((s) =>
        [
          s.ticker,
          esc(s.name),
          s.lastPrice,
          s.priceChangePct,
          s.currentRating,
          esc(s.lastSignal),
          s.daysSinceSignal === 999 ? '' : s.daysSinceSignal,
          stars[s.ticker] ? 'yes' : 'no',
        ].join(','),
      )
      const csv = [header.join(','), ...lines].join('\r\n')
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `stockpilot-watchlist-${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  const btnBase =
    'inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800'

  return (
    <div className="flex flex-col gap-5 p-4 sm:p-6">
      {/* Page header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-baseline gap-2">
          <h2 className="text-lg font-semibold text-slate-100">Watchlist</h2>
          {!loading && (
            <span className="text-sm text-slate-500">
              ({total} stocks
              {favCount > 0 && `, ${favCount} ★`})
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-full sm:w-56">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search stocks…"
              className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none"
            />
          </div>

          {/* Favorites-only toggle */}
          <button
            onClick={() => setFavoritesOnly((v) => !v)}
            className={
              'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
              (favoritesOnly
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800')
            }
            title="Show only favorites"
          >
            <Star
              size={14}
              className={favoritesOnly ? 'fill-amber-400 text-amber-400' : ''}
            />
            <span className="hidden sm:inline">Favorites</span>
          </button>

          {/* Filter dropdown */}
          <div className="relative">
            <button
              ref={filterButtonRef}
              onClick={() => setFilterOpen((v) => !v)}
              className={
                'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
                (filtersActive
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                  : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800')
              }
            >
              <SlidersHorizontal size={14} />
              <span className="hidden sm:inline">Filter</span>
              {filtersActive && (
                <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400" />
              )}
            </button>

            {filterOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setFilterOpen(false)}
                />
                {filterStyle && (
                  <div
                    style={filterStyle}
                    className="z-20 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900 p-3 shadow-xl"
                  >
                    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Minimum VSA rating
                    </p>
                    <div className="mb-3 flex flex-col gap-1">
                      {RATING_OPTIONS.map((o) => (
                        <button
                          key={o.value}
                          onClick={() => setMinRating(o.value)}
                          className={
                            'rounded-md px-2 py-1.5 text-left text-sm transition-colors ' +
                            (minRating === o.value
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : 'text-slate-300 hover:bg-slate-800')
                          }
                        >
                          {o.label}
                        </button>
                      ))}
                    </div>

                    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Signal
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {SIGNAL_OPTIONS.map((sig) => (
                        <button
                          key={sig}
                          onClick={() => setSignalFilter(sig)}
                          className={
                            'rounded-md px-2 py-1 text-xs transition-colors ' +
                            (signalFilter === sig
                              ? 'bg-emerald-500/15 text-emerald-300'
                              : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
                          }
                        >
                          {sig === 'all' ? 'All' : sig}
                        </button>
                      ))}
                    </div>

                    {filtersActive && (
                      <button
                        onClick={clearFilters}
                        className="mt-3 w-full rounded-md border border-slate-800 px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800"
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Refresh — runs the full backend pipeline (Yahoo → ratings → DB) */}
          {/* Column selector — the same choice on the table and the cards. */}
          <ColumnPicker
            value={columns.stored}
            order={columns.order}
            onToggle={columns.toggle}
            onMove={columns.move}
            onReset={columns.reset}
            customized={columns.customized}
            visibleCount={columns.count}
          />

          {/* Sort — phones/tablets only; the wide table sorts by its headers. */}
          <SortMenu
            className="lg:hidden"
            options={sortOptions}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={onSort}
            onSortDirChange={setSortDir}
          />

          <RefreshButton onRefreshed={refetch} />

          {/* Export CSV */}
          <button
            onClick={handleExport}
            disabled={total === 0 || exporting}
            className={btnBase + ' disabled:cursor-not-allowed disabled:opacity-50'}
            title="Export current view to CSV"
          >
            {exporting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Download size={14} />
            )}
            <span className="hidden sm:inline">Export</span>
          </button>
        </div>
      </div>

      {/* Loading / error states */}
      {loading && <LoadingSkeleton />}
      {error && !loading && <ErrorBanner message={error} onRetry={refetch} />}

      {/* Desktop table (lg+) and phone/tablet cards (below lg), both rendered
          from the same user-chosen column list, so hiding a column hides it in
          both layouts. */}
      {!loading && !error && rows.length > 0 && (
        <>
          <RankingTable
            columns={columns.renderColumns}
            rows={rows}
            onOpen={openTicker}
            onToggleStar={toggleStar}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={onSort}
            minWidth={tableMinWidth(columns.renderColumns)}
            footer={
              <div className="flex items-center justify-between gap-2 border-t border-slate-800 px-4 py-3 text-xs text-slate-500">
                <span>
                  {total === 0
                    ? '0 stocks'
                    : `${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, total)} of ${total} stocks`}
                </span>
                {totalPages > 1 && (
                  <Pagination
                    current={currentPage}
                    total={totalPages}
                    onChange={setCurrentPage}
                  />
                )}
              </div>
            }
          />

          <RankingCardList
            columns={columns.renderColumns}
            rows={rows}
            onOpen={openTicker}
            onToggleStar={toggleStar}
          />
        </>
      )}

      {/* Mobile / tablet pagination */}
      {!loading && !error && totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pb-2 lg:hidden">
          <Pagination
            current={currentPage}
            total={totalPages}
            onChange={setCurrentPage}
          />
        </div>
      )}

      {/* Empty states */}
      {!loading && !error && rows.length === 0 && data && (
        <div className="py-16 text-center text-slate-500">
          {favoritesOnly && favCount === 0 ? (
            <>
              <Star size={28} className="mx-auto mb-3 text-slate-600" />
              <p>
                No favorites yet — tap the{' '}
                <Star
                  size={13}
                  className="inline -translate-y-px text-amber-400"
                />{' '}
                star on a stock to add it.
              </p>
            </>
          ) : (
            <>
              No stocks match your search or filters.
              {filtersActive && (
                <button
                  onClick={clearFilters}
                  className="ml-2 text-emerald-400 hover:underline"
                >
                  Clear filters
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
