// Dashboard — the app's home page ("/"). A single ranked table with a
// segmented control at the top to switch the view between:
//   Best VSA  — highest VSA rating today (the core "best stocks" per VSA method)
//   Winners   — biggest price gainers today
//   Losers    — biggest price losers today
//   Favorites — the user's starred stocks
// All views query the live GET /api/stocks/ranking feed server-side: each tab
// maps to a sort order (plus the favorites allow-list), and search/filters are
// sent as query parameters. Rows load in pages of 25 with infinite scroll — a
// sentinel below the list fetches the next page as it comes into view.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Star,
  TrendingDown,
  TrendingUp,
  Trophy,
} from 'lucide-react'
import {
  useInfiniteRanking,
  type InfiniteRankingParams,
} from '../hooks/useRanking'
import type { RankingSortKey, SortDir } from '../api/stocksApi'
import { RefreshButton } from '../components/RefreshButton'
import { loadFavorites, saveFavorites } from '../lib/favorites'
import { deltaTone, fmtPct, fmtPrice } from '../lib/format'
import { RATING_OPTIONS, SIGNAL_OPTIONS } from '../lib/filterOptions'
import {
  InfoTip,
  RatingMeter,
  SignalBadge,
  SortHeader,
  Sparkline,
  TickerMark,
} from '../components/ui'
import type { SignalVerdict, StockRankingItem } from '../types'

type ViewId = 'best' | 'winners' | 'losers' | 'favorites'

const TABS: { id: ViewId; label: string; icon: React.ElementType }[] = [
  { id: 'best', label: 'Best VSA', icon: Trophy },
  { id: 'winners', label: 'Winners', icon: TrendingUp },
  { id: 'losers', label: 'Losers', icon: TrendingDown },
  { id: 'favorites', label: 'Favorites', icon: Star },
]

const VIEW_COPY: Record<ViewId, { title: string; subtitle: string }> = {
  best: {
    title: 'Best stocks today (VSA)',
    subtitle: 'Highest VSA rating across the GPW after the latest close.',
  },
  winners: {
    title: "Today's winners",
    subtitle: 'Largest positive price change this session.',
  },
  losers: {
    title: "Today's losers",
    subtitle: 'Largest negative price change this session.',
  },
  favorites: {
    title: 'Your favorites',
    subtitle: 'Stocks you starred, ranked by VSA rating.',
  },
}

/** Rows fetched per request — each scroll to the bottom appends one page. */
const PAGE_SIZE = 25

/* ── Server-side sorting ─────────────────────────────────────────────────── */

/** The ranking columns shown (and sortable) on this page. */
type DashboardSortKey = Extract<
  RankingSortKey,
  | 'ticker'
  | 'name'
  | 'currentRating'
  | 'lastSignal'
  | 'aiConfidence'
  | 'lastPrice'
  | 'priceChangePct'
>

/** The column each tab sorts by until the user clicks a different header. */
const TAB_DEFAULT_SORT: Record<ViewId, { sortBy: DashboardSortKey; sortDir: SortDir }> = {
  best: { sortBy: 'currentRating', sortDir: 'desc' },
  winners: { sortBy: 'priceChangePct', sortDir: 'desc' },
  losers: { sortBy: 'priceChangePct', sortDir: 'asc' },
  favorites: { sortBy: 'currentRating', sortDir: 'desc' },
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [view, setView] = useState<ViewId>('best')
  const [stars, setStars] = useState<Record<string, boolean>>(loadFavorites)

  const [query, setQuery] = useState('')
  // Debounced search text — avoids firing a request on every keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('')

  // Debounce the search box (300 ms) before it becomes a query parameter.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(query.trim()), 300)
    return () => clearTimeout(t)
  }, [query])

  const [sortBy, setSortBy] = useState<DashboardSortKey>('currentRating')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Switching tabs resets to that tab's natural sort; a header click still
  // overrides it until the tab changes again. Adjusted during render (not in
  // an effect) so the stale sort never reaches the backend as a request.
  const [prevView, setPrevView] = useState(view)
  if (view !== prevView) {
    setPrevView(view)
    setSortBy(TAB_DEFAULT_SORT[view].sortBy)
    setSortDir(TAB_DEFAULT_SORT[view].sortDir)
  }

  const [filterOpen, setFilterOpen] = useState(false)
  const [minRating, setMinRating] = useState(0)
  const [signalFilter, setSignalFilter] = useState<SignalVerdict | 'all'>('all')
  const filtersActive = minRating > 0 || signalFilter !== 'all'

  useEffect(() => {
    saveFavorites(stars)
  }, [stars])

  // Tickers currently starred — the allow-list sent to the backend when the
  // Favorites tab is active.
  const favTickers = useMemo(
    () => Object.keys(stars).filter((t) => stars[t]),
    [stars],
  )

  // Everything is computed by the backend — this hook just requests pages
  // with the right sort/filter/search, appending them as the user scrolls.
  const rankingParams = useMemo<InfiniteRankingParams>(
    () => ({
      pageSize: PAGE_SIZE,
      sortBy,
      sortDir,
      q: debouncedSearch || undefined,
      minRating: minRating || undefined,
      signal: signalFilter,
      tickers: view === 'favorites' ? favTickers : undefined,
    }),
    [sortBy, sortDir, debouncedSearch, minRating, signalFilter, view, favTickers],
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

  const copy = VIEW_COPY[view]

  return (
    <div className="flex flex-col gap-5 p-4 sm:p-6">
      {/* Header + view switcher */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="flex items-center gap-1.5 text-lg font-semibold text-slate-100">
            {copy.title}
            <InfoTip text="Stocks are ranked by their VSA rating (0–100): the volume-spread patterns of professional buying and selling, with recent signals weighted more. Configure the detection rules on the Scanner page — this list follows your settings." />
          </h2>
          <p className="text-sm text-slate-500">{copy.subtitle}</p>
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
              placeholder="Search stocks…"
              className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none"
            />
          </div>

          {/* Segmented control */}
          <div className="inline-flex rounded-lg border border-slate-800 bg-slate-900 p-1">
            {TABS.map(({ id, label, icon: Icon }) => {
              const active = view === id
              return (
                <button
                  key={id}
                  onClick={() => setView(id)}
                  className={
                    'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ' +
                    (active
                      ? 'bg-slate-800 text-slate-100 ring-1 ring-inset ring-slate-700'
                      : 'text-slate-400 hover:text-slate-200')
                  }
                >
                  <Icon
                    size={15}
                    className={active ? 'text-emerald-400' : ''}
                  />
                  <span className="hidden sm:inline">{label}</span>
                </button>
              )
            })}
          </div>

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
                <div className="absolute right-0 z-20 mt-2 w-60 rounded-lg border border-slate-800 bg-slate-900 p-3 shadow-xl">
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
          <p className="text-sm">Loading GPW rankings…</p>
        </div>
      )}

      {error && !loading && (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm">
          <span className="text-rose-300">
            <span className="font-semibold">Backend error:</span> {error}
          </span>
          <button
            onClick={refetch}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500"
          >
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      )}

      {/* ── Desktop / tablet table (md+) ─────────────────────────────────── */}
      {!loading && !error && rows.length > 0 && (
        <div className="hidden overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40 md:block">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1120px] table-fixed text-sm">
              <colgroup>
                <col className="w-10" />
                <col className="w-48" />
                <col />
                <col className="w-44" />
                <col className="w-36" />
                <col className="w-20" />
                <col className="w-32" />
                <col className="w-44" />
              </colgroup>
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3 font-medium">#</th>
                  <SortHeader
                    label="Symbol"
                    col="ticker"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Name"
                    col="name"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Rating"
                    col="currentRating"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    info="VSA score with time decay: recent bullish signals push it above 50, bearish ones below. Green above 70 (strong accumulation), red below 30 (distribution)."
                  />
                  <SortHeader
                    label="Signal"
                    col="lastSignal"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="AI"
                    col="aiConfidence"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    info="Confidence (0–100) of the built-in local AI-insight engine's verdict — computed on-device, no external service."
                  />
                  <SortHeader
                    label="Price"
                    col="lastPrice"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                  />
                  <SortHeader
                    label="Change"
                    col="priceChangePct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    subLabel="% & sparkline"
                  />
                </tr>
              </thead>
              <tbody>
                {rows.map((s, i) => (
                  <tr
                    key={s.ticker}
                    onClick={() => openTicker(s.ticker)}
                    tabIndex={0}
                    aria-label={`${s.ticker} ${s.name}, open details`}
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
                          aria-label="Toggle favorite"
                        >
                          <Star
                            size={15}
                            className={
                              s.starred ? 'fill-amber-400 text-amber-400' : ''
                            }
                          />
                        </button>
                        <TickerMark ticker={s.ticker} />
                        <span className="font-semibold text-slate-100">
                          {s.ticker}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      <span className="block truncate" title={s.name}>
                        {s.name}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <RatingMeter rating={s.currentRating} />
                    </td>
                    <td className="px-4 py-3">
                      <SignalBadge verdict={s.lastSignal} />
                    </td>
                    <td className="px-4 py-3 text-center tabular-nums text-slate-300">
                      {s.aiConfidence}%
                    </td>
                    <td className="px-4 py-3 text-right font-medium text-slate-200">
                      {fmtPrice(s.lastPrice)} PLN
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-3">
                        <Sparkline data={s.sparkline} />
                        <span
                          className={
                            'w-16 text-right text-xs ' +
                            deltaTone(s.priceChangePct)
                          }
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
                aria-label={`${s.ticker} ${s.name}, open details`}
                onClick={() => openTicker(s.ticker)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    openTicker(s.ticker)
                  }
                }}
                className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-3 transition-colors hover:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50 sm:gap-4 sm:p-4"
              >
                <span className="w-5 text-center text-sm font-semibold tabular-nums text-slate-500">
                  {i + 1}
                </span>

                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleStar(s.ticker)
                  }}
                  className="text-slate-600 hover:text-amber-400"
                  aria-label="Toggle favorite"
                >
                  <Star
                    size={15}
                    className={
                      s.starred ? 'fill-amber-400 text-amber-400' : ''
                    }
                  />
                </button>

                <TickerMark ticker={s.ticker} />

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-100">
                      {s.ticker}
                    </span>
                    <span className="truncate text-xs text-slate-500">
                      {s.name}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-3">
                    <RatingMeter rating={s.currentRating} />
                    <SignalBadge verdict={s.lastSignal} />
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    AI {s.aiConfidence}%
                  </div>
                </div>

                <div className="hidden sm:block">
                  <Sparkline data={s.sparkline} />
                </div>

                <div className="text-right">
                  <div className="font-medium text-slate-200">
                    {fmtPrice(s.lastPrice)} PLN
                  </div>
                  <div className={'text-sm ' + deltaTone(s.priceChangePct)}>
                    {fmtPct(s.priceChangePct)}
                  </div>
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
              Loading more stocks…
            </div>
          ) : (
            <p className="py-3 text-xs text-slate-600">
              Showing {rows.length} of {total} stocks
            </p>
          )}
        </div>
      )}

      {/* Empty states */}
      {!loading && !error && rows.length === 0 && items && (
        <div className="py-16 text-center text-slate-500">
          {view === 'favorites' && !filtersActive && !debouncedSearch ? (
            <>
              <Star size={28} className="mx-auto mb-3 text-slate-600" />
              <p>
                No favorites yet — tap the{' '}
                <Star
                  size={13}
                  className="inline -translate-y-px text-amber-400"
                />{' '}
                star on any stock to add it here.
              </p>
            </>
          ) : (
            <p>
              No stocks match your search or filters.
              {filtersActive && (
                <button
                  onClick={clearFilters}
                  className="ml-2 text-emerald-400 hover:underline"
                >
                  Clear filters
                </button>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
