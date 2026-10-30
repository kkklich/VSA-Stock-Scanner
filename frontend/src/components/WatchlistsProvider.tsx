import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { watchlistsRequest, type Watchlist } from '../api/watchlistsApi'
import { useAuth } from '../hooks/useAuth'
import { WatchlistsContext, useWatchlists } from '../hooks/useWatchlists'
import { loadFavorites } from '../lib/favorites'

export function WatchlistsProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth()
  const { t } = useTranslation()
  const guest = useWatchlists()
  const owner = user?.id ?? null
  const currentOwner = useRef(owner)
  currentOwner.current = owner
  const [snapshot, setSnapshot] = useState<{ owner: number; lists: Watchlist[] } | null>(null)
  const [selection, setSelection] = useState<{ owner: number; id: string } | null>(null)
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<{ owner: number; code: string } | null>(null)
  const request = useRef<symbol | null>(null)
  const controller = useRef<AbortController | null>(null)
  const knownLists = useRef<Watchlist[]>([])
  const lists = useMemo(() => snapshot?.owner === owner ? snapshot.lists : [], [snapshot, owner])
  const active = lists.find((list) => selection?.owner === owner && list.id === selection.id) ?? lists[0]
  knownLists.current = lists
  const stars = useMemo(() => Object.fromEntries((active?.tickers ?? []).map((ticker) => [ticker, true])), [active])

  const run = useCallback(async (method: string, path = '', body?: unknown, selectNew = false) => {
    if (owner === null || authLoading || request.current) return false
    const token = Symbol()
    const abort = new AbortController()
    controller.current = abort
    request.current = token
    setPending(true)
    setFailure(null)
    try {
      const result = await watchlistsRequest(method, path, body, abort.signal)
      if (currentOwner.current !== owner || request.current !== token) return false
      if (selectNew) {
        const ids = new Set(knownLists.current.map((list) => list.id))
        const added = result.find((list) => !ids.has(list.id))
        if (added) setSelection({ owner, id: added.id })
      }
      setSnapshot({ owner, lists: result })
      return true
    } catch (error) {
      if (currentOwner.current === owner && request.current === token) {
        setFailure({ owner, code: error instanceof ApiError && error.code ? error.code : 'failed' })
      }
      return false
    } finally {
      if (request.current === token) { request.current = null; setPending(false) }
    }
  }, [owner, authLoading])

  useEffect(() => {
    controller.current?.abort()
    request.current = null
    setPending(false)
    setSnapshot(null)
    setFailure(null)
    if (owner !== null) {
      try {
        const id = localStorage.getItem(`stockpilot:active-watchlist:${owner}`)
        if (id) setSelection({ owner, id })
      } catch { /* Browser storage can be unavailable. */ }
    }
    if (owner !== null && !authLoading) void run('POST', '/bootstrap', { name: t('watchlists.defaultName') })
    return () => { controller.current?.abort(); request.current = null }
    // Language changes must not discard account data or rename a saved list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [owner, authLoading, run])

  useEffect(() => {
    if (owner === null || !active) return
    try { localStorage.setItem(`stockpilot:active-watchlist:${owner}`, active.id) }
    catch { /* Selection still works for this visit. */ }
  }, [owner, active])

  useEffect(() => {
    if (owner === null || authLoading) return
    const refresh = () => {
      if (!document.hidden) void run('POST', '/bootstrap', { name: t('watchlists.defaultName') })
    }
    window.addEventListener('focus', refresh)
    const timer = window.setInterval(refresh, 60_000)
    return () => { window.removeEventListener('focus', refresh); window.clearInterval(timer) }
  }, [owner, authLoading, run, t])

  const ready = owner !== null && snapshot?.owner === owner && !!active
  const busy = authLoading || pending || (owner !== null && !ready)
  const memberPath = `/${active?.id}/members`
  const value = owner === null && !authLoading ? guest : {
    lists, activeId: active?.id ?? '', stars, busy,
    error: failure?.owner === owner ? failure.code : null,
    select: (id: string) => { if (owner !== null && !pending) setSelection({ owner, id }) },
    reload: () => { void run('POST', '/bootstrap', { name: t('watchlists.defaultName') }) },
    toggleStar: (ticker: string) => {
      if (!busy) void run(stars[ticker] ? 'DELETE' : 'PUT', memberPath, { tickers: [ticker] })
    },
    create: (name: string) => run('POST', '', { name }, true),
    rename: (name: string) => ready ? run('PATCH', `/${active.id}`, { name }) : Promise.resolve(false),
    remove: () => ready ? run('DELETE', `/${active.id}`) : Promise.resolve(false),
    importLocal: () => {
      const local = loadFavorites()
      const tickers = Object.keys(local).filter((ticker) => local[ticker])
      return ready && tickers.length ? run('PUT', memberPath, { tickers }) : Promise.resolve(false)
    },
  }
  return <WatchlistsContext.Provider value={value}>{children}</WatchlistsContext.Provider>
}
