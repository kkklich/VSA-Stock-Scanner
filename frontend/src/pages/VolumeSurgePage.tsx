// Volume Surge page — companies trading on unusually high volume right now.
// Method: multi-day relative volume (RVOL) — the average volume of the last
// few sessions divided by the stock's own baseline average before them.
// Volume is the "effort" side of VSA, so each row also shows the price change
// over the surge window (the "result") and the stock's VSA rating/verdict.

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import {
  Card,
  CompanyLink,
  InfoTip,
  MarketBadge,
  SignalBadge,
  SortHeader,
  TickerMark,
} from '../components/ui'
import { useVolumeSurge } from '../hooks/useVolumeSurge'
import { useMarketScope } from '../hooks/useMarkets'
import { ALL_MARKETS, displayTicker, GPW_MARKET } from '../lib/markets'
import { plnLine } from '../lib/rankingColumns'
import { usePersistentState } from '../hooks/usePersistentState'
import { SortMenu, type SortOption } from '../components/SortMenu'
import { useTableSort } from '../hooks/useTableSort'
import type {
  ApiVolumeSurgeItem,
  SortDir,
  VolumeSurgeSortKey,
} from '../api/stocksApi'
import type { SignalVerdict } from '../types'
import { deltaTone, fmtCompactPln, fmtMoney, fmtPct, ratingTone } from '../lib/format'

const PAGE_SIZE = 25

/** Columns that read naturally A→Z on the first click. */
const TEXT_COLUMNS: VolumeSurgeSortKey[] = ['ticker', 'name', 'sector']

const initialSortDir = (col: VolumeSurgeSortKey): SortDir =>
  TEXT_COLUMNS.includes(col) ? 'asc' : 'desc'

/** The sortable columns, labelled as their table headers are. */
const SORT_OPTIONS: SortOption<VolumeSurgeSortKey>[] = [
  { key: 'ticker', label: 'Company' },
  { key: 'sector', label: 'Sector' },
  { key: 'volumeRatio', label: 'RVOL' },
  { key: 'recentAvgVolume', label: 'Volume now / normal' },
  { key: 'daysAboveBaseline', label: 'Hot days' },
  { key: 'priceChangePct', label: 'Price move' },
  { key: 'lastPrice', label: 'Price' },
  { key: 'currentRating', label: 'VSA' },
  { key: 'lastSignal', label: 'Signal' },
]

/* ── Screen parameter presets ───────────────────────────────────────────── */

const RECENT_OPTIONS = [
  { value: 1, label: '1 day' },
  { value: 3, label: '3 days' },
  { value: 5, label: '5 days' },
  { value: 10, label: '10 days' },
]

const BASELINE_OPTIONS = [
  { value: 10, label: '10 days' },
  { value: 20, label: '20 days' },
  { value: 30, label: '30 days' },
  { value: 60, label: '60 days' },
]

const RATIO_OPTIONS = [
  { value: 1.5, label: '≥ 1.5×' },
  { value: 2, label: '≥ 2×' },
  { value: 3, label: '≥ 3×' },
  { value: 5, label: '≥ 5×' },
]

/** Attention color for the RVOL badge: the higher the ratio, the hotter. */
function ratioBadgeClass(ratio: number): string {
  if (ratio >= 3) return 'bg-amber-500/15 text-amber-400 ring-amber-500/30'
  if (ratio >= 2) return 'bg-amber-500/10 text-amber-300 ring-amber-500/20'
  return 'bg-slate-600/30 text-slate-300 ring-slate-500/30'
}

function ButtonGroup<T extends number>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-slate-700">
      {options.map((opt, i) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={
            'px-2.5 py-1.5 text-xs font-medium transition-colors ' +
            (i > 0 ? 'border-l border-slate-700 ' : '') +
            (opt.value === value
              ? 'bg-slate-700/70 text-slate-100'
              : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export function VolumeSurgePage() {
  const navigate = useNavigate()
  const [recentDays, setRecentDays] = usePersistentState(
    'stockpilot:volume-surge:recentDays',
    3,
  )
  const [baselineDays, setBaselineDays] = usePersistentState(
    'stockpilot:volume-surge:baselineDays',
    20,
  )
  const [minRatio, setMinRatio] = usePersistentState(
    'stockpilot:volume-surge:minRatio',
    1.5,
  )
  const [page, setPage] = useState(1)
  // Changing the ordering starts a fresh list: the pages accumulate, so page 2
  // of the old order can't be appended under the new one.
  const backToFirstPage = useCallback(() => setPage(1), [])
  const { sort, onSort, onSortDirChange, onRemoveLevel } =
    useTableSort<VolumeSurgeSortKey>(
      { key: 'volumeRatio', dir: 'desc' },
      initialSortDir,
      backToFirstPage,
    )

  // The top bar's market; relative volume has no unit, so "all" is fine.
  const { market } = useMarketScope({ allowAll: true })
  const marketParam = market && market !== GPW_MARKET ? market : undefined
  // Pooled, the backend orders price and volume by their value in złoty (a
  // share count × its close), so the rows print that value beneath — without
  // it a sorted column reads as unsorted.
  const pooled = market === ALL_MARKETS
  useEffect(() => {
    setPage(1)
  }, [marketParam])

  const { items, meta, loading, loadingMore, error, hasMore, refetch } =
    useVolumeSurge(
      {
        recentDays,
        baselineDays,
        minRatio,
        page,
        pageSize: PAGE_SIZE,
        sort,
        market: marketParam,
      },
      { enabled: market !== null },
    )

  const totalCount = meta?.totalCount ?? 0

  // Infinite scroll: when the sentinel row below the table scrolls into view
  // (a little before it's actually visible, via rootMargin) and there are more
  // rows to fetch, advance to the next page — the hook appends the results.
  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) return
    // Derive the next page from how many rows are already loaded rather than
    // from the previous page number: if the observer fires twice before React
    // re-renders, both calls compute the same page, so no page can be skipped.
    setPage(Math.floor(items.length / PAGE_SIZE) + 1)
  }, [loading, loadingMore, hasMore, items.length])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore()
      },
      { rootMargin: '300px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [loadMore])

  /** Change a screen parameter and start a fresh list from page 1. */
  const applyParam = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v)
    setPage(1)
  }

  return (
    <div className="space-y-4 p-4 md:p-6">
      {/* Header + how it works */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">
            Volume surge — unusually high trading volume
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-400">
            Stocks whose average volume over the last{' '}
            <span className="text-slate-200">{recentDays}</span> session
            {recentDays > 1 ? 's' : ''} is at least{' '}
            <span className="text-slate-200">{minRatio}×</span> their own average
            over the <span className="text-slate-200">{baselineDays}</span>{' '}
            sessions before that (relative volume, RVOL). In VSA terms a volume
            surge is <em>effort</em> — professional money at work; the price
            change alongside it is the <em>result</em>.
          </p>
        </div>
        {meta?.asOf && (
          <span className="text-xs text-slate-500">Data as of {meta.asOf}</span>
        )}
      </div>

      {/* Screen parameters */}
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          Surge window
          <InfoTip text="How many of the most recent sessions are averaged as the 'now' volume." />
          <ButtonGroup
            options={RECENT_OPTIONS}
            value={recentDays}
            onChange={applyParam(setRecentDays)}
          />
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          Baseline
          <InfoTip text="The reference period: how many sessions before the surge window define the stock's 'normal' volume." />
          <ButtonGroup
            options={BASELINE_OPTIONS}
            value={baselineDays}
            onChange={applyParam(setBaselineDays)}
          />
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          Min. ratio
          <InfoTip text="Only stocks whose recent volume is at least this many times the baseline are shown. 1.5× = elevated, 3× or more = a major event." />
          <ButtonGroup
            options={RATIO_OPTIONS}
            value={minRatio}
            onChange={applyParam(setMinRatio)}
          />
        </div>
        {meta && !loading && (
          <span className="ml-auto text-xs text-slate-500">
            {totalCount} of {meta.scannedCount} scanned stocks
          </span>
        )}
      </Card>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-24 text-slate-400">
          <Loader2 className="animate-spin" size={18} />
          Scanning volume…
        </div>
      ) : error && items.length === 0 ? (
        <div className="py-24 text-center text-sm text-rose-400">
          Failed to load: {error}{' '}
          <button
            type="button"
            onClick={refetch}
            className="ml-2 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            Retry
          </button>
        </div>
      ) : totalCount === 0 ? (
        <div className="py-24 text-center text-sm text-slate-400">
          No stock currently trades at {minRatio}× its normal volume. Try a
          lower minimum ratio or a shorter surge window.
        </div>
      ) : (
        <>
          {/* Sort. Shown on every screen: the wide table also sorts by its
              column headers (shift-click there adds a further level), but that
              gesture is invisible — this names the levels outright. */}
          <div className="flex justify-end">
            <SortMenu
              options={SORT_OPTIONS}
              sort={sort}
              onSort={onSort}
              onSortDirChange={onSortDirChange}
              onRemoveLevel={onRemoveLevel}
            />
          </div>

          {/* ── Desktop table (lg+) ─────────────────────────────────────────
              min-width (not an overflow wrapper) so the sticky header can pin to
              the page as you scroll; the table stays inside the card and the
              page scrolls sideways when the viewport is narrower than it. Below
              lg the table is hidden and the card list (further down) is shown,
              so phones and tablets never scroll sideways. */}
          <Card className="hidden min-w-[760px] lg:block">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-slate-500">
                  <SortHeader
                    label="Company"
                    col="ticker"
                    sort={sort}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Sector"
                    col="sector"
                    sort={sort}
                    onSort={onSort}
                    className="hidden lg:table-cell"
                  />
                  <SortHeader
                    label="RVOL"
                    col="volumeRatio"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info="Relative volume: average volume of the surge window ÷ the baseline average. 2× = double the normal activity."
                    className="text-right"
                  />
                  <SortHeader
                    label="Volume now / normal"
                    col="recentAvgVolume"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info="Average shares traded per session: during the surge window vs the baseline period."
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="Hot days"
                    col="daysAboveBaseline"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info="How many sessions of the surge window individually beat the baseline average — more days = a sustained surge, not a one-off."
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="Price move"
                    col="priceChangePct"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info="Price change across the surge window. Direction alone doesn't classify a surge in VSA: high volume on a rise can be genuine buying or a buying climax (weakness), and on a fall genuine selling or stopping volume (strength). Read it together with the VSA signal and the chart."
                    className="text-right"
                  />
                  <SortHeader
                    label="Price"
                    col="lastPrice"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    className="hidden text-right sm:table-cell"
                  />
                  <SortHeader
                    label="VSA"
                    col="currentRating"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    className="text-right"
                  />
                  <SortHeader
                    label="Signal"
                    col="lastSignal"
                    sort={sort}
                    onSort={onSort}
                    className="hidden sm:table-cell"
                  />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <SurgeRow
                    key={item.ticker}
                    item={item}
                    pooled={pooled}
                    recentDays={meta?.recentDays ?? recentDays}
                    onOpen={() => navigate(`/stock/${item.ticker.toLowerCase()}`)}
                  />
                ))}
              </tbody>
            </table>
          </Card>

          {/* ── Mobile / tablet cards (below lg) ─────────────────────────── */}
          <div className="space-y-2.5 lg:hidden">
            {items.map((item) => (
              <SurgeCard
                key={item.ticker}
                item={item}
                pooled={pooled}
                recentDays={meta?.recentDays ?? recentDays}
                onOpen={() => navigate(`/stock/${item.ticker.toLowerCase()}`)}
              />
            ))}
          </div>

          {/* Infinite-scroll footer */}
          <div className="flex flex-col items-center gap-3 pb-2">
            <span className="text-xs text-slate-500">
              Showing {items.length} of {totalCount} surging stocks
            </span>

            {/* Sentinel: scrolling this into view loads the next page. */}
            <div ref={sentinelRef} className="h-px w-full" />

            {loadingMore && (
              <span className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 className="animate-spin" size={14} />
                Loading more…
              </span>
            )}

            {error && items.length > 0 && !loadingMore && (
              <span className="text-xs text-rose-400">
                Couldn’t load more: {error}{' '}
                <button
                  type="button"
                  onClick={refetch}
                  className="ml-1 rounded-md border border-slate-700 px-2 py-0.5 text-slate-300 hover:bg-slate-800"
                >
                  Retry
                </button>
              </span>
            )}

            {!hasMore && !loadingMore && !error && (
              <span className="text-xs text-slate-600">End of results</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function SurgeRow({
  item,
  pooled,
  recentDays,
  onOpen,
}: {
  item: ApiVolumeSurgeItem
  pooled: boolean
  recentDays: number
  onOpen: () => void
}) {
  return (
    <tr
      onClick={onOpen}
      className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/40"
    >
      <td className="px-4 py-3">
        <CompanyLink
          ticker={item.ticker}
          title={item.name}
          className="flex items-center gap-2.5"
        >
          <TickerMark ticker={displayTicker(item.ticker)} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 font-semibold text-slate-100">
              {displayTicker(item.ticker)}
              <MarketBadge market={item.market} />
            </div>
            <div className="max-w-[180px] truncate text-xs text-slate-500">
              {item.name}
            </div>
          </div>
        </CompanyLink>
      </td>
      <td className="hidden px-4 py-3 text-xs text-slate-400 lg:table-cell">
        {item.sector ?? '—'}
      </td>
      <td className="px-4 py-3 text-right">
        <span
          className={
            'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset ' +
            ratioBadgeClass(item.volumeRatio)
          }
        >
          {item.volumeRatio.toFixed(1)}×
        </span>
      </td>
      <td className="hidden px-4 py-3 text-right text-xs tabular-nums md:table-cell">
        <span className="text-slate-200">{fmtCompactPln(item.recentAvgVolume)}</span>
        <span className="text-slate-500"> / {fmtCompactPln(item.baselineAvgVolume)}</span>
        {plnLine(item.recentAvgVolume * item.lastPrice, item.currency, pooled, 'turnover')}
      </td>
      <td className="hidden px-4 py-3 text-right text-xs tabular-nums text-slate-300 md:table-cell">
        {item.daysAboveBaseline}/{recentDays}
      </td>
      <td
        className={
          'px-4 py-3 text-right text-sm font-medium tabular-nums ' +
          deltaTone(item.priceChangePct)
        }
      >
        {fmtPct(item.priceChangePct)}
      </td>
      <td className="hidden px-4 py-3 text-right text-sm tabular-nums text-slate-200 sm:table-cell">
        {fmtMoney(item.lastPrice, item.currency)}
        {plnLine(item.lastPrice, item.currency, pooled)}
      </td>
      <td className="px-4 py-3 text-right">
        <span
          className={
            'inline-flex min-w-8 items-center justify-center rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset ' +
            ratingTone(item.currentRating).badge
          }
        >
          {item.currentRating}
        </span>
      </td>
      <td className="hidden px-4 py-3 sm:table-cell">
        <SignalBadge verdict={item.lastSignal as SignalVerdict} />
      </td>
    </tr>
  )
}

/** Compact card form of one surge row, shown below lg where the table is hidden. */
function SurgeCard({
  item,
  pooled,
  recentDays,
  onOpen,
}: {
  item: ApiVolumeSurgeItem
  pooled: boolean
  recentDays: number
  onOpen: () => void
}) {
  return (
    <div
      onClick={onOpen}
      role="button"
      tabIndex={0}
      aria-label={`${displayTicker(item.ticker)} ${item.name}, open details`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className="cursor-pointer rounded-xl border border-slate-800 bg-slate-900/40 p-4 transition-colors hover:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <TickerMark ticker={displayTicker(item.ticker)} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 font-semibold text-slate-100">
              {displayTicker(item.ticker)}
              <MarketBadge market={item.market} />
            </div>
            <div className="truncate text-xs text-slate-500">{item.name}</div>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <span
            className={
              'inline-flex items-center rounded-md px-2 py-0.5 text-sm font-semibold tabular-nums ring-1 ring-inset ' +
              ratioBadgeClass(item.volumeRatio)
            }
          >
            {item.volumeRatio.toFixed(1)}×
          </span>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-500">
            RVOL
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-slate-800/60 pt-2 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Price move</span>
          <span className={'tabular-nums font-medium ' + deltaTone(item.priceChangePct)}>
            {fmtPct(item.priceChangePct)}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Price</span>
          <span className="text-right tabular-nums text-slate-200">
            {fmtMoney(item.lastPrice, item.currency)}
            {plnLine(item.lastPrice, item.currency, pooled)}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Volume</span>
          <span className="text-right tabular-nums text-slate-300">
            {fmtCompactPln(item.recentAvgVolume)}
            <span className="text-slate-500">
              {' / '}
              {fmtCompactPln(item.baselineAvgVolume)}
            </span>
            {plnLine(item.recentAvgVolume * item.lastPrice, item.currency, pooled, 'turnover')}
          </span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Hot days</span>
          <span className="tabular-nums text-slate-300">
            {item.daysAboveBaseline}/{recentDays}
          </span>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3 border-t border-slate-800/60 pt-2">
        <span
          className={
            'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset ' +
            ratingTone(item.currentRating).badge
          }
        >
          VSA {item.currentRating}
        </span>
        <SignalBadge verdict={item.lastSignal as SignalVerdict} />
      </div>
    </div>
  )
}
