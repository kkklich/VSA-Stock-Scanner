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
import type { RankingSortKey, SortDir } from '../api/stocksApi'
import { RefreshButton } from '../components/RefreshButton'
import { MethodPicker } from '../components/MethodPicker'
import { CombinedScoreCell, MethodScoreCell } from '../components/MethodCells'
import { loadFavorites, saveFavorites } from '../lib/favorites'
import { deltaTone, fmtPct, fmtPrice } from '../lib/format'
import { RATING_OPTIONS, SIGNAL_OPTIONS } from '../lib/filterOptions'
import {
  CompanyLink,
  InfoTip,
  SignalBadge,
  SortHeader,
  Sparkline,
  TickerMark,
} from '../components/ui'
import type { SignalVerdict, StockRankingItem } from '../types'

/** Rows fetched per request — each scroll to the bottom appends one page. */
const PAGE_SIZE = 25

/** localStorage key for the dashboard's selected trading methods. */
const METHODS_KEY = 'stockpilot:dashboard-methods:v1'

/* ── Server-side sorting ─────────────────────────────────────────────────── */

/** The core (non per-method) columns this page can sort by. */
type DashboardSortKey = Extract<
  RankingSortKey,
  'ticker' | 'name' | 'lastSignal' | 'combinedScore' | 'lastPrice' | 'priceChangePct'
>

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
  const [sortBy, setSortBy] = useState<DashboardSortKey>('combinedScore')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const [filterOpen, setFilterOpen] = useState(false)
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
      // Send `methods` only when the user has customized the selection. While
      // "all methods" is selected (the default, including before the catalogue
      // has loaded) the param is omitted — the backend treats absent as "all"
      // — so the query key stays stable and the ranking is not refetched when
      // the catalogue resolves.
      methods:
        methodsCustomized && selectedMethods.length ? selectedMethods : undefined,
    }),
    [sortBy, sortDir, debouncedSearch, minRating, signalFilter, methodsCustomized, selectedMethods],
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

  const onSort = (col: DashboardSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      setSortDir(col === 'ticker' || col === 'name' ? 'asc' : 'desc')
    }
  }

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

  // Table min-width grows with the number of method columns so the layout
  // never crushes; the page scrolls horizontally when it exceeds the viewport.
  const tableMinWidth = 820 + selectedMethodDefs.length * 130

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

          {/* Method selector */}
          <MethodPicker
            methods={catalogue}
            selected={selectedMethods}
            onToggle={toggleMethod}
            onReset={resetMethods}
            customized={methodsCustomized}
          />

          {/* Filter dropdown */}
          <div className="relative">
            <button
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
                <div className="absolute right-0 z-20 mt-2 w-60 rounded-lg border border-slate-800 bg-slate-900 p-3 shadow-xl">
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

      {/* ── Desktop / tablet table (md+) ─────────────────────────────────── */}
      {/* No overflow wrapper: the table scrolls with the page so its header can
          stay pinned (position: sticky) as you scroll; min-width keeps the
          columns from crushing and grows with the number of method columns. */}
      {!loading && !error && rows.length > 0 && (
        <div
          className="hidden rounded-xl border border-slate-800 bg-slate-900/40 md:block"
          style={{ minWidth: tableMinWidth }}
        >
          <table className="w-full text-sm" style={{ minWidth: tableMinWidth }}>
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="sticky top-0 z-10 bg-slate-900 px-4 py-3 font-medium shadow-[inset_0_-1px_0_#1e293b]">
                  #
                </th>
                <SortHeader
                  label={t('dashboard.cols.symbol')}
                  col="ticker"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                />
                <SortHeader
                  label={t('dashboard.cols.name')}
                  col="name"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                />
                <SortHeader
                  label={t('dashboard.cols.signal')}
                  col="lastSignal"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                />
                {/* One header per selected method (not server-sortable yet). */}
                {selectedMethodDefs.map((m) => (
                  <th
                    key={m.id}
                    className="sticky top-0 z-10 bg-slate-900 px-4 py-3 font-medium shadow-[inset_0_-1px_0_#1e293b]"
                  >
                    <span className="inline-flex items-center gap-1 text-right normal-case">
                      <span className="whitespace-normal leading-tight">{m.name}</span>
                      <InfoTip
                        align="center"
                        text={`${m.description}  ·  ${t('dashboard.methodSource')} ${m.source}`}
                      />
                    </span>
                  </th>
                ))}
                <SortHeader
                  label={t('dashboard.cols.combined')}
                  col="combinedScore"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  info={t('dashboard.combinedInfo')}
                />
                <SortHeader
                  label={t('dashboard.cols.price')}
                  col="lastPrice"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align="right"
                />
                <SortHeader
                  label={t('dashboard.cols.change')}
                  col="priceChangePct"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align="right"
                  subLabel={t('dashboard.cols.changeSub')}
                />
              </tr>
            </thead>
            <tbody>
              {rows.map((s, i) => (
                <tr
                  key={s.ticker}
                  onClick={() => openTicker(s.ticker)}
                  tabIndex={0}
                  aria-label={t('dashboard.openDetails', { ticker: s.ticker, name: s.name })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      openTicker(s.ticker)
                    }
                  }}
                  className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/30 focus:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50"
                >
                  <td className="px-4 py-3 text-center tabular-nums text-slate-500">
                    {i + 1}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleStar(s.ticker)
                        }}
                        className="text-slate-600 hover:text-amber-400"
                        aria-label={t('dashboard.toggleFavorite')}
                      >
                        <Star
                          size={15}
                          className={s.starred ? 'fill-amber-400 text-amber-400' : ''}
                        />
                      </button>
                      <CompanyLink
                        ticker={s.ticker}
                        title={s.name}
                        className="flex items-center gap-2.5 font-semibold text-slate-100"
                      >
                        <TickerMark ticker={s.ticker} />
                        {s.ticker}
                      </CompanyLink>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    <CompanyLink
                      ticker={s.ticker}
                      title={s.name}
                      className="block max-w-[220px] truncate hover:text-slate-200"
                    >
                      {s.name}
                    </CompanyLink>
                  </td>
                  <td className="px-4 py-3">
                    <SignalBadge verdict={s.lastSignal} />
                  </td>
                  {selectedMethodDefs.map((m) => (
                    <td key={m.id} className="px-4 py-3 text-right">
                      <MethodScoreCell result={s.methodResults[m.id]} />
                    </td>
                  ))}
                  <td className="px-4 py-3">
                    <CombinedScoreCell score={s.combinedScore} />
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-slate-200">
                    {fmtPrice(s.lastPrice)} {t('common.pln')}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-3">
                      <Sparkline data={s.sparkline} />
                      <span
                        className={'w-16 text-right text-xs ' + deltaTone(s.priceChangePct)}
                      >
                        {fmtPct(s.priceChangePct)}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Mobile cards (below md) ──────────────────────────────────────── */}
      {!loading && !error && rows.length > 0 && (
        <ul className="flex flex-col gap-2 md:hidden">
          {rows.map((s, i) => (
            <li key={s.ticker}>
              <div
                role="button"
                tabIndex={0}
                aria-label={t('dashboard.openDetails', { ticker: s.ticker, name: s.name })}
                onClick={() => openTicker(s.ticker)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    openTicker(s.ticker)
                  }
                }}
                className="flex cursor-pointer flex-col gap-2 rounded-xl border border-slate-800 bg-slate-900/40 p-3 transition-colors hover:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50"
              >
                <div className="flex items-center gap-3">
                  <span className="w-5 text-center text-sm font-semibold tabular-nums text-slate-500">
                    {i + 1}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      toggleStar(s.ticker)
                    }}
                    className="text-slate-600 hover:text-amber-400"
                    aria-label={t('dashboard.toggleFavorite')}
                  >
                    <Star
                      size={15}
                      className={s.starred ? 'fill-amber-400 text-amber-400' : ''}
                    />
                  </button>
                  <TickerMark ticker={s.ticker} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-100">{s.ticker}</span>
                      <span className="truncate text-xs text-slate-500">{s.name}</span>
                    </div>
                    <div className="mt-1">
                      <SignalBadge verdict={s.lastSignal} />
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium text-slate-200">
                      {fmtPrice(s.lastPrice)} {t('common.pln')}
                    </div>
                    <div className={'text-sm ' + deltaTone(s.priceChangePct)}>
                      {fmtPct(s.priceChangePct)}
                    </div>
                  </div>
                </div>

                {/* Combined + per-method scores */}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-slate-800/60 pt-2">
                  <span className="flex items-center gap-1.5 text-xs text-slate-500">
                    {t('dashboard.cols.combined')}
                    <CombinedScoreCell score={s.combinedScore} />
                  </span>
                  {selectedMethodDefs.map((m) => (
                    <span key={m.id} className="flex items-center gap-1.5 text-xs text-slate-500">
                      {m.name.split(' ')[0]}
                      <MethodScoreCell result={s.methodResults[m.id]} />
                    </span>
                  ))}
                </div>
              </div>
            </li>
          ))}
        </ul>
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

      {/* Empty state */}
      {!loading && !error && rows.length === 0 && items && (
        <div className="py-16 text-center text-slate-500">
          <p>
            {t('dashboard.emptyNoMatch')}
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
