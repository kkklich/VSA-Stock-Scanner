// Star toggle for one company — the same favorites list the Dashboard and
// Watchlist use (account list or guest localStorage), so starring a stock here
// shows up there and vice versa.

import { useTranslation } from 'react-i18next'
import { Star } from 'lucide-react'
import { useWatchlists } from '../hooks/useWatchlists'
import { WatchlistControls } from './WatchlistControls'

export function FavoriteButton({ ticker }: { ticker: string }) {
  const { t } = useTranslation()
  const { stars, toggleStar, busy } = useWatchlists()
  const starred = stars[ticker] ?? false

  const label = starred ? t('chart.removeFavorite') : t('chart.addFavorite')

  return (
    <div className="flex flex-wrap items-center gap-2">
    <WatchlistControls compact />
    <button
      type="button"
      onClick={() => toggleStar(ticker)}
      disabled={busy}
      aria-pressed={starred}
      aria-label={label}
      title={label}
      className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-amber-400"
    >
      <Star
        size={20}
        className={starred ? 'fill-amber-400 text-amber-400' : ''}
      />
    </button>
    </div>
  )
}
