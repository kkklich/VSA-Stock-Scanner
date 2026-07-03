// Dashboard — the app's home page ("/"). A single ranked list with a segmented
// control at the top to switch the view between:
//   Best VSA  — highest VSA rating today (the core "best stocks" per VSA method)
//   Winners   — biggest price gainers today
//   Losers    — biggest price losers today
//   Favorites — the user's starred stocks
// All views are derived from the live GET /api/stocks/ranking feed.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Loader2,
  RefreshCw,
  Star,
  TrendingDown,
  TrendingUp,
  Trophy,
} from 'lucide-react'
import { useRanking } from '../hooks/useRanking'
import { loadFavorites, saveFavorites } from '../lib/favorites'
import { deltaTone, fmtPct, fmtPrice } from '../lib/format'
import {
  InfoTip,
  RatingMeter,
  SignalBadge,
  Sparkline,
  TickerMark,
} from '../components/ui'
import type { StockRankingItem } from '../types'

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

const TOP_N = 10

export function DashboardPage() {
  const navigate = useNavigate()
  const { data, loading, error, refetch } = useRanking()
  const [view, setView] = useState<ViewId>('best')
  const [stars, setStars] = useState<Record<string, boolean>>(loadFavorites)

  useEffect(() => {
    saveFavorites(stars)
  }, [stars])

  const toggleStar = (ticker: string) =>
    setStars((p) => ({ ...p, [ticker]: !p[ticker] }))

  const openTicker = (ticker: string) => navigate(`/stock/${ticker.toLowerCase()}`)

  const rows = useMemo<StockRankingItem[]>(() => {
    if (!data) return []
    const withStars = data.map((s) => ({ ...s, starred: stars[s.ticker] ?? false }))
    switch (view) {
      case 'best':
        return [...withStars]
          .sort((a, b) => b.currentRating - a.currentRating)
          .slice(0, TOP_N)
      case 'winners':
        return [...withStars]
          .sort((a, b) => b.priceChangePct - a.priceChangePct)
          .slice(0, TOP_N)
      case 'losers':
        return [...withStars]
          .sort((a, b) => a.priceChangePct - b.priceChangePct)
          .slice(0, TOP_N)
      case 'favorites':
        return withStars
          .filter((s) => s.starred)
          .sort((a, b) => b.currentRating - a.currentRating)
    }
  }, [data, view, stars])

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

        <div className="flex items-center gap-2">
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
          <button
            onClick={refetch}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            title="Refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
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

      {/* List */}
      {!loading && !error && rows.length > 0 && (
        <ul className="flex flex-col gap-2">
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
                  <div className="mt-1 hidden items-center gap-3 sm:flex">
                    <RatingMeter rating={s.currentRating} />
                    <SignalBadge verdict={s.lastSignal} />
                  </div>
                </div>

                <div className="hidden md:block">
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

      {/* Empty states */}
      {!loading && !error && rows.length === 0 && data && (
        <div className="py-16 text-center text-slate-500">
          {view === 'favorites' ? (
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
            <p>No data available.</p>
          )}
        </div>
      )}
    </div>
  )
}
