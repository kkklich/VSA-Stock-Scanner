// Volume Surge page — companies trading on unusually high volume right now.
// Method: multi-day relative volume (RVOL) — the average volume of the last
// few sessions divided by the stock's own baseline average before them.
// Volume is the "effort" side of VSA, so each row also shows the price change
// over the surge window (the "result") and the stock's VSA rating/verdict.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import {
  Card,
  InfoTip,
  Pagination,
  SignalBadge,
  SortHeader,
  TickerMark,
} from '../components/ui'
import { useVolumeSurge } from '../hooks/useVolumeSurge'
import type {
  ApiVolumeSurgeItem,
  SortDir,
  VolumeSurgeSortKey,
} from '../api/stocksApi'
import type { SignalVerdict } from '../types'
import { deltaTone, fmtCompactPln, fmtPct, fmtPrice, ratingTone } from '../lib/format'

const PAGE_SIZE = 25

/** Columns that read naturally A→Z on the first click. */
const TEXT_COLUMNS: VolumeSurgeSortKey[] = ['ticker', 'name', 'sector']

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
  const [recentDays, setRecentDays] = useState(3)
  const [baselineDays, setBaselineDays] = useState(20)
  const [minRatio, setMinRatio] = useState(1.5)
  const [sortBy, setSortBy] = useState<VolumeSurgeSortKey>('volumeRatio')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)

  const { data, loading, error, refetch } = useVolumeSurge({
    recentDays,
    baselineDays,
    minRatio,
    page,
    pageSize: PAGE_SIZE,
    sortBy,
    sortDir,
  })

  const items = data?.items ?? []
  const totalCount = data?.totalCount ?? 0
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))

  /** Change a screen parameter and jump back to the first page. */
  const applyParam = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v)
    setPage(1)
  }

  const onSort = (col: VolumeSurgeSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      setSortDir(TEXT_COLUMNS.includes(col) ? 'asc' : 'desc')
    }
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
        {data?.asOf && (
          <span className="text-xs text-slate-500">Data as of {data.asOf}</span>
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
        {data && !loading && (
          <span className="ml-auto text-xs text-slate-500">
            {totalCount} of {data.scannedCount} scanned stocks
          </span>
        )}
      </Card>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-24 text-slate-400">
          <Loader2 className="animate-spin" size={18} />
          Scanning volume across the GPW…
        </div>
      ) : error ? (
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
      ) : items.length === 0 ? (
        <div className="py-24 text-center text-sm text-slate-400">
          No stock currently trades at {minRatio}× its normal volume. Try a
          lower minimum ratio or a shorter surge window.
        </div>
      ) : (
        <>
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-500">
                  <SortHeader
                    label="Company"
                    col="ticker"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Sector"
                    col="sector"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    className="hidden lg:table-cell"
                  />
                  <SortHeader
                    label="RVOL"
                    col="volumeRatio"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Relative volume: average volume of the surge window ÷ the baseline average. 2× = double the normal activity."
                    className="text-right"
                  />
                  <SortHeader
                    label="Volume now / normal"
                    col="recentAvgVolume"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Average shares traded per session: during the surge window vs the baseline period."
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="Hot days"
                    col="daysAboveBaseline"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="How many sessions of the surge window individually beat the baseline average — more days = a sustained surge, not a one-off."
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="Price move"
                    col="priceChangePct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Price change across the surge window. High volume on a rising price reads as buying (strength); on a falling price as selling — though in VSA extreme volume on a fall can also mark a selling climax."
                    className="text-right"
                  />
                  <SortHeader
                    label="Price"
                    col="lastPrice"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    className="hidden text-right sm:table-cell"
                  />
                  <SortHeader
                    label="VSA"
                    col="currentRating"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    className="text-right"
                  />
                  <SortHeader
                    label="Signal"
                    col="lastSignal"
                    sortBy={sortBy}
                    sortDir={sortDir}
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
                    recentDays={data?.recentDays ?? recentDays}
                    onOpen={() => navigate(`/stock/${item.ticker.toLowerCase()}`)}
                  />
                ))}
              </tbody>
            </table>
          </Card>

          {/* Pager */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-2">
            <span className="text-xs text-slate-500">
              Showing {(page - 1) * PAGE_SIZE + 1}–
              {Math.min(page * PAGE_SIZE, totalCount)} of {totalCount} surging
              stocks
            </span>
            {totalPages > 1 && (
              <Pagination current={page} total={totalPages} onChange={setPage} />
            )}
          </div>
        </>
      )}
    </div>
  )
}

function SurgeRow({
  item,
  recentDays,
  onOpen,
}: {
  item: ApiVolumeSurgeItem
  recentDays: number
  onOpen: () => void
}) {
  return (
    <tr
      onClick={onOpen}
      className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/40"
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2.5">
          <TickerMark ticker={item.ticker} />
          <div className="min-w-0">
            <div className="font-semibold text-slate-100">{item.ticker}</div>
            <div className="max-w-[180px] truncate text-xs text-slate-500">
              {item.name}
            </div>
          </div>
        </div>
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
        {fmtPrice(item.lastPrice)}
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
