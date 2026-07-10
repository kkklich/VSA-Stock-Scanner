// Refresh button + "last updated" caption, shared by Dashboard and Watchlist.
//
// One click runs the FULL backend refresh pipeline: download fresh quotes from
// Yahoo Finance → recalculate every stock's VSA rating → save the daily rating
// snapshots to the database (that saved history feeds the "Rating history"
// chart on the stock detail page). While the pipeline runs the icon spins and
// the caption says what's happening; when it finishes the page refetches.

import { RefreshCw } from 'lucide-react'
import { useRefresh } from '../hooks/useRefresh'
import { fmtRefreshTime } from '../lib/format'

export function RefreshButton({ onRefreshed }: { onRefreshed: () => void }) {
  const { refreshing, status, error, refresh } = useRefresh(onRefreshed)

  const caption = refreshing
    ? 'Downloading & recalculating…'
    : error
      ? 'Refresh failed'
      : status?.lastRefreshAt
        ? `Updated ${fmtRefreshTime(status.lastRefreshAt)}`
        : null

  const title = error
    ? `Refresh failed: ${error}`
    : 'Download fresh data from Yahoo Finance and recalculate all VSA ratings. ' +
      'Data updates automatically once a day after the GPW close (18:00).'

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={refresh}
        disabled={refreshing}
        title={title}
        className={
          'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
          (error && !refreshing
            ? 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
            : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 disabled:cursor-wait disabled:opacity-70')
        }
      >
        <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
        <span className="hidden sm:inline">Refresh</span>
      </button>
      {caption && (
        <span
          className={
            'hidden whitespace-nowrap text-xs md:inline ' +
            (error && !refreshing
              ? 'text-rose-400'
              : refreshing
                ? 'text-emerald-400'
                : 'text-slate-500')
          }
        >
          {caption}
        </span>
      )}
    </div>
  )
}
