import { apiFetch } from './client'

export interface Watchlist { id: string; name: string; tickers: string[] }

export function watchlistsRequest(method: string, path = '', body?: unknown, signal?: AbortSignal) {
  return apiFetch<Watchlist[]>(`/api/watchlists${path}`, {
    method, signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
}
