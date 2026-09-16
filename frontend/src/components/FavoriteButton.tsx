// Star toggle for one company — the same favorites list the Dashboard and
// Watchlist use (localStorage, `lib/favorites.ts`), so starring a stock here
// shows up there and vice versa.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Star } from 'lucide-react'
import { loadFavorites, saveFavorites } from '../lib/favorites'

export function FavoriteButton({ ticker }: { ticker: string }) {
  const { t } = useTranslation()
  // Re-read on every toggle so a star set on another page (or tab) since this
  // one mounted is never overwritten with a stale copy.
  const [starred, setStarred] = useState(() => loadFavorites()[ticker] ?? false)

  const toggle = () => {
    const map = loadFavorites()
    const next = !map[ticker]
    if (next) map[ticker] = true
    else delete map[ticker]
    saveFavorites(map)
    setStarred(next)
  }

  const label = starred ? t('chart.removeFavorite') : t('chart.addFavorite')

  return (
    <button
      type="button"
      onClick={toggle}
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
  )
}
