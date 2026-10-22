import { useCallback, useEffect, useState } from 'react'
import { fetchFinancialHistory, fetchLongTermHistory, fetchLongTermRanking } from '../api/longTermApi'
import type { FinancialObservation, HistoryResponse, LongTermRanking, LongTermSnapshot } from '../types/longTerm'
import { useDataVersion } from './useDataVersion'

export const LONG_TERM_REQUEST_TIMEOUT_MS = 30_000
const MAX_CACHED_KEYS = 32

interface CachedResource<T> {
  data: T
  lastUpdated: string
  stale: boolean
}

interface ResourceState<T> {
  key: string | null
  data: T | null
  lastUpdated: string | null
  stale: boolean
  error: boolean
  loading: boolean
}

// Separate resource caches prevent a ticker's score history from ever becoming
// its financial history. These retain successful results only for this tab.
const rankingCache = new Map<string, CachedResource<LongTermRanking>>()
const scoreCache = new Map<string, CachedResource<HistoryResponse<LongTermSnapshot>>>()
const financialCache = new Map<string, CachedResource<HistoryResponse<FinancialObservation>>>()

function remember<T>(cache: Map<string, CachedResource<T>>, key: string, entry: CachedResource<T>) {
  cache.delete(key)
  cache.set(key, entry)
  if (cache.size > MAX_CACHED_KEYS) cache.delete(cache.keys().next().value!)
}

/** Test helper, matching the data-version hook's reset convention. */
export function resetLongTermCacheForTests() {
  rankingCache.clear()
  scoreCache.clear()
  financialCache.clear()
}

/** Keep previous data during refresh, but never show a previous market/ticker. */
function useResource<T>(
  key: string | null,
  fetcher: (key: string, signal: AbortSignal) => Promise<T>,
  cache: Map<string, CachedResource<T>>,
) {
  const version = useDataVersion()
  const [retry, setRetry] = useState(0)
  const [state, setState] = useState<ResourceState<T>>({
    key: null, data: null, lastUpdated: null, stale: false, error: false, loading: false,
  })
  useEffect(() => {
    if (key === null) return
    const controller = new AbortController()
    let active = true
    const cached = cache.get(key)
    if (cached) remember(cache, key, cached)
    setState((previous) => {
      const retained = cached ?? (previous.key === key ? previous : null)
      return {
        key, data: retained?.data ?? null, lastUpdated: retained?.lastUpdated ?? null,
        stale: retained?.stale ?? false, error: false, loading: true,
      }
    })

    const fail = () => {
      if (!active) return
      active = false
      clearTimeout(timeout)
      controller.abort()
      const retained = cache.get(key)
      if (retained) remember(cache, key, { ...retained, stale: true })
      setState((previous) => previous.key === key
        ? { ...previous, loading: false, error: true, stale: previous.data !== null }
        : previous)
    }
    // End loading explicitly: abort alone cannot settle a hung response body,
    // auth retry, or a fetch implementation that does not honor its signal.
    const timeout = setTimeout(fail, LONG_TERM_REQUEST_TIMEOUT_MS)
    void (async () => {
      try {
        const data = await fetcher(key, controller.signal)
        if (!active) return
        active = false
        clearTimeout(timeout)
        const loaded = { data, lastUpdated: new Date().toISOString(), stale: false }
        remember(cache, key, loaded)
        setState({ key, ...loaded, loading: false, error: false })
      } catch {
        fail()
      }
    })()
    return () => {
      active = false
      clearTimeout(timeout)
      controller.abort()
    }
  }, [key, fetcher, cache, version, retry])
  const refetch = useCallback(() => setRetry((value) => value + 1), [])
  const visible = key === null ? null : state.key === key ? state : cache.get(key)
  return {
    data: visible?.data ?? null,
    loading: key !== null && (state.key !== key || state.loading),
    error: key !== null && state.key === key && state.error,
    // Client acquisition time. It is neither a price session nor the source's
    // financial observation time, and must be labelled "Last loaded" in UI.
    lastUpdated: visible?.lastUpdated ?? null,
    stale: visible?.stale ?? false,
    refetch,
  }
}

export function useLongTermRanking(market: string | null) {
  return useResource(market, fetchLongTermRanking, rankingCache)
}

export function useLongTermHistory(ticker: string | null) {
  return useResource(ticker, fetchLongTermHistory, scoreCache)
}

export function useFinancialHistory(ticker: string | null) {
  return useResource(ticker, fetchFinancialHistory, financialCache)
}
