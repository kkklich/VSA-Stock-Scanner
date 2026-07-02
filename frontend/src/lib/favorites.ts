// Single source of truth for the user's favorite (starred) tickers.
// Persisted in localStorage so favorites survive reloads and are shared across
// the Dashboard and Watchlist pages.

export const FAVORITES_KEY = 'stockpilot:favorites'

export type FavoritesMap = Record<string, boolean>

/** Read the persisted favorites map (safe if localStorage is unavailable). */
export function loadFavorites(): FavoritesMap {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY)
    return raw ? (JSON.parse(raw) as FavoritesMap) : {}
  } catch {
    return {}
  }
}

/** Persist the favorites map (ignores quota / private-mode errors). */
export function saveFavorites(map: FavoritesMap): void {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(map))
  } catch {
    /* ignore */
  }
}
