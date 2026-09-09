// Refresh button + "last updated" caption, shared by Dashboard and Watchlist.
//
// One click runs the FULL backend refresh pipeline: download fresh quotes from
// Yahoo Finance → recalculate every stock's VSA rating → save the daily rating
// snapshots to the database (that saved history feeds the "Rating history"
// chart on the stock detail page). While the pipeline runs the icon spins and
// the caption says what's happening; when it finishes the page refetches.

import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRefresh } from '../hooks/useRefresh'
import { fmtRefreshTime } from '../lib/format'

export function RefreshButton({ onRefreshed }: { onRefreshed: () => void }) {
  const { t } = useTranslation()
  const { refreshing, status, error, refresh } = useRefresh(onRefreshed)

  const caption = refreshing
    ? t('refresh.running')
    : error
      ? t('refresh.failed')
      : status?.lastRefreshAt
        ? t('refresh.updated', { time: fmtRefreshTime(status.lastRefreshAt) })
        : null

  const title = error ? t('refresh.titleFailed', { error }) : t('refresh.title')

  return (
    <div className="flex items-center gap-2">
      {/* Icon only — the tooltip (and the screen-reader label) carry the word.
          The caption beside it already says when the data was last refreshed. */}
      <button
        onClick={refresh}
        disabled={refreshing}
        title={title}
        aria-label={t('refresh.button')}
        className={
          'inline-flex items-center justify-center rounded-lg border p-2.5 text-sm transition-colors ' +
          (error && !refreshing
            ? 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
            : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 disabled:cursor-wait disabled:opacity-70')
        }
      >
        <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
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
