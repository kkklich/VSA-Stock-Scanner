// Volume Surge page — companies trading on unusually high volume right now.
// Relative volume (RVOL) compares recent sessions or weeks with the stock's
// typical (median) volume per session or week in the preceding baseline.
// Volume is the "effort" side of VSA, so each row also shows the price change
// over the surge window (the "result"), the bar that carried the surge
// read the way VSA reads a bar (spread and close), whether the price left its
// range, a report date when one explains the surge, and the stock's VSA
// rating/verdict with the age of the signal behind it.

import { CLASSIC_VSA_ENABLED } from '../lib/methodStatus'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FileText, Loader2, Star } from 'lucide-react'
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
import { useWatchlists } from '../hooks/useWatchlists'
import { WatchlistControls } from '../components/WatchlistControls'
import { ALL_MARKETS, displayTicker, GPW_MARKET } from '../lib/markets'
import { plnLine } from '../lib/rankingColumns'
import { useUrlState, booleanParam, enumParam, numberParam, type UrlField } from '../hooks/useUrlState'
import { sortParam } from '../lib/urlSort'
import { SortMenu, type SortOption } from '../components/SortMenu'
import { useTableSort } from '../hooks/useTableSort'
import type {
  ApiVolumeSurgeItem,
  SortDir,
  VolumeSurgeSortKey,
} from '../api/stocksApi'
import type { SignalVerdict } from '../types'
import { deltaTone, fmtCompactPln, fmtMoney, fmtPct, ratingTone } from '../lib/format'
import {
  describePeakBar,
  fmtSessionDay,
  peakBarDetail,
  signalAge,
  signalAgeLabel,
  signalAgeText,
} from '../lib/volumeSurge'

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
  { key: 'daysAboveBaseline', label: 'Above normal' },
  { key: 'peakVolumeRatio', label: 'Peak volume' },
  { key: 'priceChangePct', label: 'Price move' },
  { key: 'lastPrice', label: 'Price' },
  ...(CLASSIC_VSA_ENABLED ? [{ key: 'currentRating' as const, label: 'VSA' }] : []),
  ...(CLASSIC_VSA_ENABLED ? [{ key: 'lastSignal' as const, label: 'Signal' }] : []),
]

/* ── Screen parameter presets ───────────────────────────────────────────── */

const RECENT_DAYS = [1, 2, 3, 5, 10, 15, 20]
const BASELINE_DAYS = [10, 20, 30, 40, 60, 120, 250]
const RECENT_WEEKS = [1, 2, 3, 4, 8, 12]
const BASELINE_WEEKS = [4, 8, 13, 26, 52]

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
          aria-pressed={opt.value === value}
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

const FILTER_SELECT_CLASS = 'rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-200'

function WindowSelect({
  label,
  options,
  unit,
  value,
  onChange,
}: {
  label: string
  options: number[]
  unit: 'session' | 'week'
  value: number
  onChange: (value: number) => void
}) {
  return (
    <label className="flex items-center gap-2 text-xs text-slate-400">
      {label}
      <select className={FILTER_SELECT_CLASS} value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {options.map((count) => (
          <option key={count} value={count}>
            {count} {unit}{count === 1 ? '' : 's'}
          </option>
        ))}
      </select>
    </label>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

// Keep existing browser preferences as a fallback; URLs carry explicit values
// so opening the same link in another browser restores the same screen.
function volumeParam(key: string, fallback: number, values: number[]): UrlField<number> {
  const codec = numberParam(fallback, { values })
  return {
    read(params, name) {
      if (params.has(name)) return codec.read(params, name)
      try {
        const stored = JSON.parse(localStorage.getItem(key) ?? 'null')
        return typeof stored === 'number' && values.includes(stored) ? stored : fallback
      } catch { return fallback }
    },
    write(params, name, value) { params.set(name, String(value)) },
  }
}

const URL_FIELDS = {
  favorites: booleanParam(),
  timeframe: enumParam<'daily' | 'weekly'>('daily', ['daily', 'weekly']),
  recentDays: volumeParam('stockpilot:volume-surge:recentDays', 3, RECENT_DAYS),
  baselineDays: volumeParam('stockpilot:volume-surge:baselineDays', 20, BASELINE_DAYS),
  recentWeeks: numberParam(1, { values: RECENT_WEEKS }),
  baselineWeeks: numberParam(13, { values: BASELINE_WEEKS }),
  minRatio: volumeParam('stockpilot:volume-surge:minRatio', 1.5, [1.5, 2, 3, 5]),
  sort: sortParam<VolumeSurgeSortKey>({ key: 'volumeRatio', dir: 'desc' }, [
    'ticker', 'name', 'sector', 'lastPrice', 'recentAvgVolume', 'baselineAvgVolume',
    'volumeRatio', 'lastDayRatio', 'daysAboveBaseline', 'peakVolumeRatio',
    'priceChangePct', 'currentRating', 'lastSignal',
  ]),
}

export function VolumeSurgePage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { stars, busy: watchlistsBusy } = useWatchlists()
  const url = useUrlState(URL_FIELDS)
  const [favoritesOnly, setFavoritesOnly] = url.field('favorites')
  const favTickers = useMemo(
    () => Object.keys(stars).filter((ticker) => stars[ticker]).sort(),
    [stars],
  )
  const favoritesKey = favoritesOnly ? favTickers.join(',') : undefined
  const [timeframe, setTimeframe] = url.field('timeframe')
  const [recentDays, setRecentDays] = url.field('recentDays')
  const [baselineDays, setBaselineDays] = url.field('baselineDays')
  const [recentWeeks, setRecentWeeks] = url.field('recentWeeks')
  const [baselineWeeks, setBaselineWeeks] = url.field('baselineWeeks')
  const [minRatio, setMinRatio] = url.field('minRatio')
  const weekly = timeframe === 'weekly'
  const unit = weekly ? 'week' : 'session'
  const recentCount = weekly ? recentWeeks : recentDays
  const baselineCount = weekly ? baselineWeeks : baselineDays
  useEffect(() => {
    try {
      localStorage.setItem('stockpilot:volume-surge:recentDays', JSON.stringify(recentDays))
      localStorage.setItem('stockpilot:volume-surge:baselineDays', JSON.stringify(baselineDays))
      localStorage.setItem('stockpilot:volume-surge:minRatio', JSON.stringify(minRatio))
    } catch { /* Storage may be unavailable. */ }
  }, [recentDays, baselineDays, minRatio])
  const [page, setPage] = useState(1)
  // Changing the ordering starts a fresh list: the pages accumulate, so page 2
  // of the old order can't be appended under the new one.
  const backToFirstPage = useCallback(() => setPage(1), [])
  const { sort, onSort, onSortDirChange, onRemoveLevel } =
    useTableSort<VolumeSurgeSortKey>(
      { key: 'volumeRatio', dir: 'desc' },
      initialSortDir,
      backToFirstPage,
      url.field('sort'),
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
  }, [marketParam, favoritesKey, timeframe, recentCount, baselineCount, minRatio, sort])

  const { items, meta, loading, loadingMore, error, hasMore, refetch } =
    useVolumeSurge(
      {
        ...(weekly ? { recentWeeks, baselineWeeks } : { recentDays, baselineDays }),
        minRatio,
        page,
        pageSize: PAGE_SIZE,
        sort,
        market: marketParam,
        tickers: favoritesOnly ? favTickers : undefined,
      },
      { enabled: market !== null && (!favoritesOnly || !watchlistsBusy) },
    )

  const totalCount = meta?.totalCount ?? 0
  const resultUnit = meta ? (meta.recentWeeks != null ? 'week' : 'session') : unit
  const resultRecentCount = meta?.recentWeeks ?? meta?.recentDays ?? recentCount
  const resultBaselineCount = meta?.baselineWeeks ?? meta?.baselineDays ?? baselineCount

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
            <span className="text-slate-200">{recentCount}</span> {unit}
            {recentCount > 1 ? 's' : ''} is at least{' '}
            <span className="text-slate-200">{minRatio}×</span> their typical
            {' '}{unit} over the <span className="text-slate-200">{baselineCount}</span>{' '}
            {unit}s before that (relative volume, RVOL).
          </p>
          {weekly && (
            <p className="mt-1 max-w-3xl text-xs text-slate-400">
              For a 1W chart spike, start with a 1-week surge window and a 13-week baseline.
              The current week uses volume so far.
            </p>
          )}
        </div>
        {meta?.asOf && (
          <span className="text-xs text-slate-500">Data as of {meta.asOf}</span>
        )}
      </div>

      {/* Screen parameters */}
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Timeframe
          <select
            className={FILTER_SELECT_CLASS}
            value={timeframe}
            onChange={(e) => applyParam(setTimeframe)(e.target.value === 'weekly' ? 'weekly' : 'daily')}
          >
            <option value="daily">Daily (1D)</option>
            <option value="weekly">Weekly (1W)</option>
          </select>
        </label>
        <WindowSelect
          label="Surge window"
          options={weekly ? RECENT_WEEKS : RECENT_DAYS}
          unit={unit}
          value={recentCount}
          onChange={applyParam(weekly ? setRecentWeeks : setRecentDays)}
        />
        <WindowSelect
          label="Baseline"
          options={weekly ? BASELINE_WEEKS : BASELINE_DAYS}
          unit={unit}
          value={baselineCount}
          onChange={applyParam(weekly ? setBaselineWeeks : setBaselineDays)}
        />
        <div className="flex items-center gap-2 text-xs text-slate-400">
          Min. ratio
          <InfoTip text={`Minimum recent volume relative to a typical ${unit} in the baseline. 1.5× means 50% above normal.`} />
          <ButtonGroup
            options={RATIO_OPTIONS}
            value={minRatio}
            onChange={applyParam(setMinRatio)}
          />
        </div>
        <button
          type="button"
          onClick={() => { setFavoritesOnly((value) => !value); setPage(1) }}
          aria-pressed={favoritesOnly}
          title={t('dashboard.favoritesTooltip')}
          className={
            'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors ' +
            (favoritesOnly
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
              : 'border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800')
          }
        >
          <Star size={14} aria-hidden className={favoritesOnly ? 'fill-amber-400 text-amber-400' : ''} />
          {t('dashboard.favorites')}
          {favTickers.length > 0 && (
            <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
              {favTickers.length}
            </span>
          )}
        </button>
        {meta && !loading && (
          <span className="ml-auto text-xs text-slate-500">
            {totalCount} of {meta.scannedCount} scanned stocks
          </span>
        )}
      </Card>

      {favoritesOnly && <WatchlistControls compact />}

      {/* Results */}
      {loading || (favoritesOnly && watchlistsBusy) ? (
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
          {favoritesOnly
            ? favTickers.length === 0
              ? t('dashboard.emptyNoFavorites')
              : t('volumeSurge.emptyFavorites')
            : <>No stock currently trades at {minRatio}× its normal volume. Try a
              lower minimum ratio or a shorter surge window.</>}
          {favoritesOnly && (
            <button
              type="button"
              onClick={() => { setFavoritesOnly(false); setPage(1) }}
              className="mt-2 block w-full text-xs text-amber-400 hover:text-amber-300"
            >
              {t('dashboard.showAll')}
            </button>
          )}
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
          <Card className="hidden min-w-[800px] lg:block">
            <table className="w-full min-w-[800px] text-left text-sm">
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
                    className="hidden min-[1500px]:table-cell"
                  />
                  <SortHeader
                    label="RVOL"
                    col="volumeRatio"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info={`Average volume in the surge window divided by the median volume per ${resultUnit} in the baseline. 2× means double the normal activity.`}
                    className="text-right"
                  />
                  <SortHeader
                    label="Volume now / normal"
                    col="recentAvgVolume"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info={`Average shares traded per ${resultUnit} in the surge window compared with the median in the baseline.`}
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="Above normal"
                    col="daysAboveBaseline"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info={`Number of ${resultUnit}s in the surge window whose volume exceeded the baseline median.`}
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="Peak volume"
                    col="peakVolumeRatio"
                    sort={sort}
                    onSort={onSort}
                    info={`The highest-volume ${resultUnit} in the surge window. The bar's high-to-low range is measured against the baseline average (wide at 1.5× or more, narrow at 0.7× or less). Its close position shows where it finished within that range.`}
                  />
                  <SortHeader
                    label="Price move"
                    col="priceChangePct"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    info="Price change across the surge window. Direction alone doesn't classify a surge in VSA: high volume on a rise can be genuine buying or a buying climax (weakness), and on a fall genuine selling or stopping volume (strength). Read it together with the VSA signal and the chart. A range tag means the surge pushed the price above the highest high, or below the lowest low, of the reference period."
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
                  {CLASSIC_VSA_ENABLED && (
                  <SortHeader
                    label="VSA"
                    col="currentRating"
                    sort={sort}
                    onSort={onSort}
                    align="right"
                    className="text-right"
                  />
                  )}
                  {CLASSIC_VSA_ENABLED && (
                  <SortHeader
                    label="Signal"
                    col="lastSignal"
                    sort={sort}
                    onSort={onSort}
                    info="The stock's VSA verdict — a score over its signals of the last four months, not a reading of the surge alone. The line under it says how old the latest signal is and whether it happened during the surge."
                    className="hidden sm:table-cell"
                  />
                  )}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <SurgeRow
                    key={item.ticker}
                    item={item}
                    pooled={pooled}
                    unit={resultUnit}
                    recentCount={resultRecentCount}
                    baselineCount={resultBaselineCount}
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
                unit={resultUnit}
                recentCount={resultRecentCount}
                baselineCount={resultBaselineCount}
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

/* ── Surge context (roadmap #15b) ───────────────────────────────────────── */

/** A company report lines up with the surge — the commonest explanation. */
function ReportChip({ date }: { date: string }) {
  return (
    <span
      title={`Company report dated ${fmtSessionDay(date)}. Earnings are the most common cause of a multi-day volume surge, so this one may simply be the market digesting the results.`}
      className="inline-flex shrink-0 items-center gap-0.5 rounded border border-violet-500/30 bg-violet-500/10 px-1 py-px text-[9px] font-semibold leading-none tracking-wide text-violet-400"
    >
      <FileText size={9} aria-hidden />
      REPORT
    </span>
  )
}

/** "↑ 20-session high" when the surge pushed the price out of its range. */
function RangeBreak({
  item,
  baselineCount,
  unit,
}: {
  item: ApiVolumeSurgeItem
  baselineCount: number
  unit: 'session' | 'week'
}) {
  if (!item.breaksHigh && !item.breaksLow) return null
  const tag = (arrow: string, word: string) => (
    <span
      key={word}
      title={`During the surge the price traded ${word === 'high' ? 'above the highest high' : 'below the lowest low'} of the ${baselineCount} ${unit}s before it.`}
      className="inline-flex items-center whitespace-nowrap rounded border border-slate-700 bg-slate-800/60 px-1 py-px text-[10px] font-medium leading-none text-slate-300"
    >
      {arrow} {baselineCount}-{unit} {word}
    </span>
  )
  return (
    <span className="mt-1 flex flex-wrap justify-end gap-1">
      {item.breaksHigh && tag('↑', 'high')}
      {item.breaksLow && tag('↓', 'low')}
    </span>
  )
}

/** The highest-volume bar's date, volume and VSA shape. */
function PeakBar({
  item,
  unit,
  align = 'left',
}: {
  item: ApiVolumeSurgeItem
  unit: 'session' | 'week'
  align?: 'left' | 'right'
}) {
  const arrow = item.peakChangePct > 0 ? '▲' : item.peakChangePct < 0 ? '▼' : '•'
  const date = fmtSessionDay(item.peakDate)
  return (
    <div className={align === 'right' ? 'text-right' : ''} title={peakBarDetail(item, unit)}>
      <div className="whitespace-nowrap text-xs tabular-nums">
        <span className="text-slate-200">{unit === 'week' ? `Through ${date}` : date}</span>
        <span className="text-slate-500"> · {item.peakVolumeRatio.toFixed(1)}×</span>
      </div>
      <div className="mt-0.5 text-[11px] text-slate-400">
        <span className={deltaTone(item.peakChangePct)}>{arrow}</span>{' '}
        {describePeakBar(item)}
      </div>
    </div>
  )
}

/** How old the signal behind the verdict is, relative to the surge. */
function SignalAgeLine({ item }: { item: ApiVolumeSurgeItem }) {
  return (
    <div
      title={signalAgeText(item)}
      className={
        'mt-1 text-[11px] ' +
        (signalAge(item).kind === 'inSurge' ? 'text-slate-300' : 'text-slate-500')
      }
    >
      {signalAgeLabel(item)}
    </div>
  )
}

function SurgeRow({
  item,
  pooled,
  unit,
  recentCount,
  baselineCount,
  onOpen,
}: {
  item: ApiVolumeSurgeItem
  pooled: boolean
  unit: 'session' | 'week'
  recentCount: number
  baselineCount: number
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
              {item.reportDate && <ReportChip date={item.reportDate} />}
            </div>
            <div className="max-w-[150px] truncate text-xs text-slate-500">
              {item.name}
            </div>
          </div>
        </CompanyLink>
      </td>
      <td className="hidden px-4 py-3 text-xs text-slate-400 min-[1500px]:table-cell">
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
        {item.daysAboveBaseline}/{recentCount}
      </td>
      <td className="px-4 py-3">
        <PeakBar item={item} unit={unit} />
      </td>
      <td className="px-4 py-3 text-right">
        <span
          className={'text-sm font-medium tabular-nums ' + deltaTone(item.priceChangePct)}
        >
          {fmtPct(item.priceChangePct)}
        </span>
        <RangeBreak item={item} baselineCount={baselineCount} unit={unit} />
      </td>
      <td className="hidden px-4 py-3 text-right text-sm tabular-nums text-slate-200 sm:table-cell">
        {fmtMoney(item.lastPrice, item.currency)}
        {plnLine(item.lastPrice, item.currency, pooled)}
      </td>
      {CLASSIC_VSA_ENABLED && <>
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
        <SignalAgeLine item={item} />
      </td>
      </>}
    </tr>
  )
}

/** Compact card form of one surge row, shown below lg where the table is hidden. */
function SurgeCard({
  item,
  pooled,
  unit,
  recentCount,
  baselineCount,
  onOpen,
}: {
  item: ApiVolumeSurgeItem
  pooled: boolean
  unit: 'session' | 'week'
  recentCount: number
  baselineCount: number
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
              {item.reportDate && <ReportChip date={item.reportDate} />}
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
          <span className="text-right">
            <span className={'tabular-nums font-medium ' + deltaTone(item.priceChangePct)}>
              {fmtPct(item.priceChangePct)}
            </span>
            <RangeBreak item={item} baselineCount={baselineCount} unit={unit} />
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
          <span className="text-slate-500">Above normal</span>
          <span className="tabular-nums text-slate-300">
            {item.daysAboveBaseline}/{recentCount}
          </span>
        </div>
        <div className="col-span-2 flex justify-between gap-2">
          <span className="text-slate-500">Peak volume</span>
          <PeakBar item={item} unit={unit} align="right" />
        </div>
      </div>

      {CLASSIC_VSA_ENABLED && (
      <div className="mt-2 flex items-center justify-between gap-3 border-t border-slate-800/60 pt-2">
        <span
          className={
            'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset ' +
            ratingTone(item.currentRating).badge
          }
        >
          VSA {item.currentRating}
        </span>
        <div className="text-right">
          <SignalBadge verdict={item.lastSignal as SignalVerdict} />
          <SignalAgeLine item={item} />
        </div>
      </div>
      )}
    </div>
  )
}
