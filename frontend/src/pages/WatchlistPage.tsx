// Watchlist / ranking table page. The center "master" view of the master–detail
// dashboard (DOCUMENTATION.md §3). Client-side search + sort over mock data.
// Responsive: a full table on md+ screens, stacked cards on phones.

import { useMemo, useState } from 'react'
import {
  ArrowDownUp,
  Download,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Star,
} from 'lucide-react'
import { mockRanking } from '../data/mockData'
import type { StockRankingItem } from '../types'
import { deltaTone, fmtPct, fmtPrice } from '../lib/format'
import { RatingMeter, SignalBadge, Sparkline } from '../components/ui'

/** Colored initial bubble standing in for a company logo. */
function TickerMark({ ticker }: { ticker: string }) {
  const palette = [
    'from-sky-400 to-sky-600',
    'from-violet-400 to-violet-600',
    'from-amber-400 to-amber-600',
    'from-emerald-400 to-emerald-600',
    'from-rose-400 to-rose-600',
    'from-indigo-400 to-indigo-600',
  ]
  const idx =
    ticker.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % palette.length
  return (
    <div
      className={
        'grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br text-[10px] font-bold text-slate-950 ' +
        palette[idx]
      }
    >
      {ticker.slice(0, 1)}
    </div>
  )
}

export function WatchlistPage({
  onSelect,
}: {
  onSelect: (ticker: string) => void
}) {
  const [query, setQuery] = useState('')
  const [stars, setStars] = useState<Record<string, boolean>>(
    Object.fromEntries(mockRanking.map((s) => [s.ticker, s.starred]))
  )

  const toggleStar = (ticker: string) =>
    setStars((p) => ({ ...p, [ticker]: !p[ticker] }))

  const rows = useMemo<StockRankingItem[]>(() => {
    const q = query.trim().toLowerCase()
    const filtered = q
      ? mockRanking.filter(
          (s) =>
            s.ticker.toLowerCase().includes(q) ||
            s.name.toLowerCase().includes(q)
        )
      : mockRanking
    return [...filtered].sort((a, b) => b.currentRating - a.currentRating)
  }, [query])

  const StarButton = ({ ticker }: { ticker: string }) => (
    <button
      onClick={(e) => {
        e.stopPropagation()
        toggleStar(ticker)
      }}
      className="text-slate-600 hover:text-amber-400"
      aria-label="Toggle watchlist"
    >
      <Star
        size={15}
        className={stars[ticker] ? 'fill-amber-400 text-amber-400' : ''}
      />
    </button>
  )

  return (
    <div className="flex flex-col gap-5 p-4 sm:p-6">
      {/* Page header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-baseline gap-2">
          <h2 className="text-lg font-semibold text-slate-100">Watchlist</h2>
          <span className="text-sm text-slate-500">({rows.length} Stocks)</span>
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
          <button className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500">
            <Plus size={15} /> Add Stock
          </button>
          <button className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800">
            <Pencil size={14} /> <span className="hidden sm:inline">Edit</span>
          </button>
          <button className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800">
            <SlidersHorizontal size={14} />{' '}
            <span className="hidden sm:inline">Filter</span>
          </button>
          <button className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-800">
            <Download size={14} />{' '}
            <span className="hidden sm:inline">Export</span>
          </button>
        </div>
      </div>

      {/* ── Desktop / tablet table (md+) ─────────────────────────────────── */}
      <div className="hidden overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40 md:block">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3 font-medium">
                  <span className="inline-flex items-center gap-1">
                    Symbol <ArrowDownUp size={12} className="text-slate-600" />
                  </span>
                </th>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 text-right font-medium">Last Price</th>
                <th className="px-4 py-3 font-medium">Rating (0–100)</th>
                <th className="px-4 py-3 font-medium">Last Signal</th>
                <th className="px-4 py-3 font-medium">Days Since Signal</th>
                <th className="px-4 py-3 text-right font-medium">
                  Change
                  <span className="block text-[10px] normal-case text-slate-600">
                    +/- % &amp; sparkline
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr
                  key={s.ticker}
                  onClick={() => onSelect(s.ticker)}
                  className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/30"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <StarButton ticker={s.ticker} />
                      <TickerMark ticker={s.ticker} />
                      <span className="font-semibold text-slate-100">
                        {s.ticker}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-400">{s.name}</td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-medium text-slate-200">
                      ${fmtPrice(s.lastPrice)}
                    </span>
                    <span
                      className={'ml-2 text-xs ' + deltaTone(s.priceChangePct)}
                    >
                      {fmtPct(s.priceChangePct)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <RatingMeter rating={s.currentRating} />
                  </td>
                  <td className="px-4 py-3">
                    <SignalBadge verdict={s.lastSignal} />
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {s.daysSinceSignal}{' '}
                    {s.daysSinceSignal === 1 ? 'day' : 'days'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-3">
                      <Sparkline data={s.sparkline} />
                      <span
                        className={
                          'w-14 text-right text-xs ' +
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

        {/* Pagination footer */}
        <div className="flex items-center justify-end gap-1 border-t border-slate-800 px-4 py-3 text-xs text-slate-500">
          <span className="mr-2">
            1–{rows.length} of {rows.length}
          </span>
          <button className="grid h-7 w-7 place-items-center rounded-md bg-emerald-600 font-medium text-white">
            1
          </button>
          <button className="grid h-7 w-7 place-items-center rounded-md hover:bg-slate-800">
            2
          </button>
          <button className="grid h-7 w-7 place-items-center rounded-md hover:bg-slate-800">
            3
          </button>
        </div>
      </div>

      {/* ── Mobile cards (below md) ──────────────────────────────────────── */}
      <div className="space-y-3 md:hidden">
        {rows.map((s) => (
          <div
            key={s.ticker}
            onClick={() => onSelect(s.ticker)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onSelect(s.ticker)
            }}
            className="w-full cursor-pointer rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-left transition-colors hover:bg-slate-800/30"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <StarButton ticker={s.ticker} />
                <TickerMark ticker={s.ticker} />
                <div>
                  <div className="font-semibold text-slate-100">{s.ticker}</div>
                  <div className="text-xs text-slate-500">{s.name}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="font-medium text-slate-200">
                  ${fmtPrice(s.lastPrice)}
                </div>
                <div className={'text-xs ' + deltaTone(s.priceChangePct)}>
                  {fmtPct(s.priceChangePct)}
                </div>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between gap-3">
              <RatingMeter rating={s.currentRating} />
              <Sparkline data={s.sparkline} />
            </div>

            <div className="mt-3 flex items-center justify-between">
              <SignalBadge verdict={s.lastSignal} />
              <span className="text-xs text-slate-500">
                {s.daysSinceSignal} {s.daysSinceSignal === 1 ? 'day' : 'days'} ago
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
