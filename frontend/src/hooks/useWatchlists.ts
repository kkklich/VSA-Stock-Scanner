import { createContext, useContext, useEffect, useState } from 'react'
import type { Watchlist } from '../api/watchlistsApi'
import { loadFavorites, saveFavorites, type FavoritesMap } from '../lib/favorites'

export interface WatchlistsState {
  lists: Watchlist[]
  activeId: string
  select: (id: string) => void
  stars: FavoritesMap
  toggleStar: (ticker: string) => void
  busy: boolean
  error: string | null
  reload: () => void
  create: (name: string) => Promise<boolean>
  rename: (name: string) => Promise<boolean>
  remove: () => Promise<boolean>
  importLocal: () => Promise<boolean>
}

export const WatchlistsContext = createContext<WatchlistsState | null>(null)

export function useWatchlists() {
  const context = useContext(WatchlistsContext)
  const [local, setLocal] = useState(loadFavorites)
  useEffect(() => {
    const sync = () => setLocal(loadFavorites())
    window.addEventListener('storage', sync)
    window.addEventListener('stockpilot:favorites-changed', sync)
    window.addEventListener('focus', sync)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('stockpilot:favorites-changed', sync)
      window.removeEventListener('focus', sync)
    }
  }, [])
  // Also supports components mounted without the app provider in tests.
  return context ?? {
    lists: [], activeId: '', select: () => {}, stars: local, busy: false, error: null,
    toggleStar: (ticker: string) => {
      const next = { ...loadFavorites() }
      if (next[ticker]) delete next[ticker]
      else next[ticker] = true
      saveFavorites(next)
      setLocal(next)
    },
    reload: () => {}, create: async () => false, rename: async () => false,
    remove: async () => false, importLocal: async () => false,
  }
}
