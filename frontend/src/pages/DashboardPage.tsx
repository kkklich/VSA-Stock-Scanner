// Dashboard — the app's home page ("/"). A ranked, multi-method list of GPW
// stocks. Beyond the core VSA rating it can show one column per selected
// trading method (VSA, Minervini Trend Template, …) plus a "Combined" column
// that ranks companies across all the chosen methods together. The user picks
// which methods appear via the Methods selector; the choice is sent to
// GET /api/stocks/ranking (server-side sorted, filtered and paginated) and
// persisted per browser. Rows load in pages of 25 with infinite scroll.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, RefreshCw, Search, SlidersHorizontal, Star } from 'lucide-react'
import {
  useInfiniteRanking,
  type InfiniteRankingParams,
} from '../hooks/useRanking'
import { useMethods } from '../hooks/useMethods'
import { usePersistentState } from '../hooks/usePersistentState'
import { sortOptionsFrom, useRankingColumns } from '../hooks/useRankingColumns'
import type { RankingSortKey, SortDir } from '../api/stocksApi'
import { RefreshButton } from '../components/RefreshButton'
import { ColumnPicker } from '../components/ColumnPicker'
import { MethodPicker } from '../components/MethodPicker'
import { RankingCardList, RankingTable } from '../components/RankingTable'
import { SortMenu } from '../components/SortMenu'
import { CombinedScoreCell, MethodScoreCell } from '../components/MethodCells'
import { loadFavorites, saveFavorites } from '../lib/favorites'
import { RATING_OPTIONS, SIGNAL_OPTIONS } from '../lib/filterOptions'
import {
  initialSortDir,
  spliceAfter,
  tableMinWidth,
  type RenderColumn,
} from '../lib/rankingColumns'
import { DisclaimerNote, InfoTip } from '../components/ui'
import type { SignalVerdict, StockRankingItem } from '../types'
import { useDropdownPosition } from '../hooks/useDropdownPosition'

/** Rows fetched per request — each scroll to the bottom appends one page. */
const PAGE_SIZE = 25

/** localStorage key for the dashboard's selected trading methods. */
const METHODS_KEY = 'stockpilot:dashboard-methods:v1'

/** Width the leading rank ("#") column adds to the table's minimum width. */
const RANK_COLUMN_WIDTH = 60

/** Width one per-method (or the combined) score column gets. */
const METHOD_COLUMN_WIDTH = 130

export function DashboardPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [stars, setStars] = useState<Record<string, boolean>>(loadFavorites)

  const [query, setQuery] = useState('')
  // Debounced search text — avoids firing a request on every keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('')

  // Debounce the search box (300 ms) before it becomes a query parameter.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(query.trim()), 300)
    return () => clearTimeout(timer)
  }, [query])

  // The combined cross-method score is the headline ranking by default.
  const [sortBy, setSortBy] = useState<RankingSortKey>('combinedScore')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // "Favorites only": narrows the ranking to the starred tickers. The stars
  // live in localStorage, so the allow-list is sent to the backend as
  // `tickers` rather than filtered client-side (which would only ever see the
  // pages already scrolled into view).
  const [favoritesOnly, setFavoritesOnly] = useState(false)

  const [filterOpen, setFilterOpen] = useState(false)
  const { buttonRef: filterButtonRef, style: filterStyle } =
    useDropdownPosition(filterOpen, 240)
  const [minRating, setMinRating] = useState(0)
  const [signalFilter, setSignalFilter] = useState<SignalVerdict | 'all'>('all')
  const filtersActive = minRating > 0 || signalFilter !== 'all'

  // Trading-method catalogue + the user's column selection. `null` = untouched,
  // which means "show every method"; an explicit array (even empty) is a choice.
  const { methods: catalogue } = useMethods()
  const [storedMethods, setStoredMethods] = usePersistentState<string[] | null>(
    METHODS_KEY,
    null,
  )
  const allMethodIds = useMemo(() => catalogue.map((m) => m.id), [catalogue])
  // Effective selection, in catalogue (display) order.
  const selectedMethods = useMemo(() => {
    const chosen = storedMethods ?? allMethodIds
    const set = new Set(chosen)
    return allMethodIds.filter((id) => set.has(id))
  }, [storedMethods, allMethodIds])
  const selectedMethodDefs = useMemo(
    () => catalogue.filter((m) => selectedMethods.includes(m.id)),
    [catalogue, selectedMethods],
  )
  const methodsCustomized = storedMethods !== null

  const toggleMethod = (id: string) => {
    setStoredMethods((prev) => {
      const base = prev ?? allMethodIds
      return base.includes(id) ? base.filter((m) => m !== id) : [...base, id]
    })
  }
  const resetMethods = () => setStoredMethods(null)

  useEffect(() => {
    saveFavorites(stars)
  }, [stars])

  // Tickers currently starred — the allow-list sent to the backend while the
  // favorites-only view is on. An empty list legitimately matches nothing.
  const favTickers = useMemo(
    () => Object.keys(stars).filter((ticker) => stars[ticker]),
    [stars],
  )
  const favCount = favTickers.length

  // Everything is computed by the backend — this hook just requests pages
  // with the right sort/filter/search/methods, appending them as the user
  // scrolls. `methods` drives the combined score and its sort.
  const rankingParams = useMemo<InfiniteRankingParams>(
    () => ({
      pageSize: PAGE_SIZE,
      sortBy,
      sortDir,
      q: debouncedSearch || undefined,
      minRating: minRating || undefined,
      signal: signalFilter,
      tickers: favoritesOnly ? favTickers : undefined,
      // Send `methods` only when the user has customized the selection. While
      // "all methods" is selected (the default, including before the catalogue
      // has loaded) the param is omitted — the backend treats absent as "all"
      // — so the query key stays stable and the ranking is not refetched when
      // the catalogue resolves.
      methods:
        methodsCustomized && selectedMethods.length ? selectedMethods : undefined,
    }),
    [
      sortBy,
      sortDir,
      debouncedSearch,
      minRating,
      signalFilter,
      favoritesOnly,
      favTickers,
      methodsCustomized,
      selectedMethods,
    ],
  )
  const {
    items,
    total,
    loading,
    loadingMore,
    hasMore,
    error,
    loadMore,
    refetch,
  } = useInfiniteRanking(rankingParams)

  const toggleStar = (ticker: string) =>
    setStars((p) => ({ ...p, [ticker]: !p[ticker] }))

  const openTicker = (ticker: string) => navigate(`/stock/${ticker.toLowerCase()}`)

  const onSort = (col: RankingSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      setSortDir(initialSortDir(col))
    }
  }

  // Which columns to show — shared with the Watchlist and Filters pages.
  const columns = useRankingColumns()

  // VSA is both a registry column (the rating meter) and a trading method, so
  // selecting both would print the same 0–100 score twice. The registry column
  // wins when it is on — its "fired N days ago" half is already the Days-ago
  // column — and the method column takes over when the user hides it.
  const ratingColumnShown = columns.renderColumns.some((c) => c.key === 'rating')

  // One column per selected trading method, plus the combined cross-method
  // score. These are built here rather than in the registry because they
  // depend on the catalogue the backend advertises; they travel down the same
  // render path as the registry columns, so they appear in the card list too.
  const methodColumns = useMemo<RenderColumn[]>(
    () => [
      // Hiding VSA's column here is display-only: the combined score is still
      // computed by the backend over every selected method.
      ...selectedMethodDefs
        .filter((m) => !(ratingColumnShown && m.id === 'vsa'))
        .map(
          (m): RenderColumn => ({
            key: m.id,
            label: m.name,
            info: `${m.description}  ·  ${t('dashboard.methodSource')} ${m.source}`,
            // Per-method scores are computed per row, not sorted by the backend.
            sortKey: null,
            align: 'right' as const,
            width: METHOD_COLUMN_WIDTH,
            headerClassName: 'normal-case',
            cell: (row) => <MethodScoreCell result={row.methodResults[m.id]} />,
          }),
        ),
      {
        key: 'combined',
        label: t('dashboard.cols.combined'),
        info: t('dashboard.combinedInfo'),
        sortKey: 'combinedScore' as const,
        align: 'left' as const,
        width: METHOD_COLUMN_WIDTH,
        cell: (row) => <CombinedScoreCell score={row.combinedScore} />,
      },
    ],
    [selectedMethodDefs, ratingColumnShown, t],
  )

  // Method columns sit next to the Signal they qualify, not at the far right.
  const tableColumns = useMemo(
    () => spliceAfter(columns.renderColumns, 'signal', methodColumns),
    [columns.renderColumns, methodColumns],
  )

  // The card list below `lg` has no headers to tap, so its sort menu offers
  // whatever the table headers would have — the columns the user kept.
  const sortOptions = useMemo(
    () => sortOptionsFrom(tableColumns, sortBy, t),
    [tableColumns, sortBy, t],
  )

  const clearFilters = () => {
    setMinRating(0)
    setSignalFilter('all')
  }

  // Overlay the client-only "starred" flag onto the rows fetched so far.
  const rows = useMemo<StockRankingItem[]>(
    () =>
      (items ?? []).map((s) => ({ ...s, starred: stars[s.ticker] ?? false })),
    [items, stars],
  )

  // Infinite scroll: when the sentinel below the list enters the viewport,
  // fetch the next page. The effect re-arms after each load, so scrolling
  // keeps appending pages until every matching row is shown.
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasMore || loading || loadingMore || error) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) loadMore()
      },
      // Start loading shortly before the user actually reaches the bottom.
      { rootMargin: '400px 0px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loading, loadingMore, error, loadMore])


  return (
    <div className="flex flex-col gap-5 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="flex items-center gap-1.5 text-lg font-semibold text-slate-100">
            {t('dashboard.heading')}
            <InfoTip text={t('dashboard.headingInfo')} />
          </h2>
          <p className="text-sm text-slate-500">{t('dashboard.subtitle')}</p>
          <DisclaimerNote className="mt-1" />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative w-full sm:w-56">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('dashboard.searchPlaceholder')}
              className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none"
            />
          </div>

          {/* Favorites-only toggle — the starred companies, nothing else. */}
          <button
            type="button"
            onClick={() => setFavoritesOnly((v) => !v)}
            aria-pressed={favoritesOnly}
            title={t('dashboard.favoritesTooltip')}
            className={
              'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
              (favoritesOnly
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800')
            }
          >
            <Star
              size={14}
              className={favoritesOnly ? 'fill-amber-400 text-amber-400' : ''}
            />
            <span className="hidden sm:inline">{t('dashboard.favorites')}</span>
            {favCount > 0 && (
              <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
                {favCount}
              </span>
            )}
          </button>

          {/* Method selector */}
          <MethodPicker
            methods={catalogue}
            selected={selectedMethods}
            onToggle={toggleMethod}
            onReset={resetMethods}
            customized={methodsCustomized}
          />

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

          {/* Sort — phones/tablets only; the wide-screen table sorts by its
              column headers instead. */}
          <SortMenu
            className="lg:hidden"
            options={sortOptions}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={onSort}
            onSortDirChange={setSortDir}
          />

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
              <span className="hidden sm:inline">{t('dashboard.filter')}</span>
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
                      {t('dashboard.minRating')}
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
                      {t('dashboard.signal')}
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
                          {sig === 'all' ? t('dashboard.all') : sig}
                        </button>
                      ))}
                    </div>

                    {filtersActive && (
                      <button
                        onClick={clearFilters}
                        className="mt-3 w-full rounded-md border border-slate-800 px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800"
                      >
                        {t('dashboard.clearFilters')}
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          <RefreshButton onRefreshed={refetch} />
        </div>
      </div>

      {/* States */}
      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-400">
          <Loader2 size={34} className="animate-spin text-emerald-500" />
          <p className="text-sm">{t('dashboard.loading')}</p>
        </div>
      )}

      {error && !loading && (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm">
          <span className="text-rose-300">
            <span className="font-semibold">{t('dashboard.backendError')}</span> {error}
          </span>
          <button
            onClick={refetch}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500"
          >
            <RefreshCw size={13} /> {t('common.retry')}
          </button>
        </div>
      )}

      {/* Desktop table (lg+) and phone/tablet cards (below lg) — both
          rendered from the same column list, so hiding a column in the picker
          hides it in both layouts. The per-method columns are spliced in right
          after the Signal they qualify. */}
      {!loading && !error && rows.length > 0 && (
        <>
          <RankingTable
            columns={tableColumns}
            rows={rows}
            onOpen={openTicker}
            onToggleStar={toggleStar}
            showRank
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={onSort}
            minWidth={tableMinWidth(tableColumns, RANK_COLUMN_WIDTH)}
          />

          <RankingCardList
            columns={tableColumns}
            rows={rows}
            onOpen={openTicker}
            onToggleStar={toggleStar}
            showRank
          />
        </>
      )}

      {/* Infinite-scroll sentinel: fetches the next page when scrolled into
          view, then shows progress under the list. */}
      {!loading && !error && rows.length > 0 && (
        <div className="flex flex-col items-center">
          <div ref={sentinelRef} aria-hidden className="h-px w-full" />
          {loadingMore ? (
            <div className="flex items-center gap-2 py-3 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin text-emerald-500" />
              {t('dashboard.loadingMore')}
            </div>
          ) : (
            <p className="py-3 text-xs text-slate-600">
              {t('dashboard.showing', { shown: rows.length, total })}
            </p>
          )}
        </div>
      )}

      {/* Empty state. "No favorites yet" is its own message: the list isn't
          empty because nothing matched, it's empty because nothing was starred
          — so it explains how to star a company instead. */}
      {!loading && !error && rows.length === 0 && items && (
        <div className="py-16 text-center text-slate-500">
          <p>
            {favoritesOnly && favCount === 0
              ? t('dashboard.emptyNoFavorites')
              : t('dashboard.emptyNoMatch')}
            {favoritesOnly && (
              <button
                onClick={() => setFavoritesOnly(false)}
                className="ml-2 text-emerald-400 hover:underline"
              >
                {t('dashboard.showAll')}
              </button>
            )}
            {filtersActive && (
              <button
                onClick={clearFilters}
                className="ml-2 text-emerald-400 hover:underline"
              >
                {t('dashboard.clearFilters')}
              </button>
            )}
          </p>
        </div>
      )}
    </div>
  )
}
