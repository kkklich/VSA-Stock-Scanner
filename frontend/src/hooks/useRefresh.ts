// Custom hook: drive the backend data-refresh pipeline from a Refresh button.
//
// Pressing Refresh POSTs /api/stocks/refresh, which makes the backend download
// fresh data from Yahoo Finance, recalculate every stock's VSA rating and save
// the daily rating snapshots to the database. The hook then polls the status
// endpoint until the run finishes and finally calls `onDone` so the caller can
// refetch its data.
//
// On mount it reads the current status once — so the "last updated" time is
// shown right away, and a refresh already running (e.g. the nightly job or a
// refresh started on another page) is picked up and followed to completion.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchRefreshStatus,
  triggerRefresh,
  type ApiRefreshStatus,
} from '../api/stocksApi'

const POLL_INTERVAL_MS = 2_500

export interface UseRefreshResult {
  /** True while the backend pipeline is running. */
  refreshing: boolean
  /** Latest known status (null until the first status fetch resolves). */
  status: ApiRefreshStatus | null
  /** Error from triggering/polling the refresh, if any. */
  error: string | null
  /** Start a refresh (no-op if one is already running). */
  refresh: () => void
}

export function useRefresh(onDone?: () => void): UseRefreshResult {
  const [refreshing, setRefreshing] = useState(false)
  const [status, setStatus] = useState<ApiRefreshStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Keep the latest onDone without making it a dependency of the polling loop.
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const timerRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  const stopPolling = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const poll = useCallback(() => {
    stopPolling()
    timerRef.current = window.setTimeout(async () => {
      try {
        const s = await fetchRefreshStatus()
        if (!mountedRef.current) return
        setStatus(s)
        if (s.state === 'running') {
          poll()
        } else {
          setRefreshing(false)
          if (s.lastError) setError(s.lastError)
          onDoneRef.current?.()
        }
      } catch (err: unknown) {
        if (!mountedRef.current) return
        setRefreshing(false)
        setError(err instanceof Error ? err.message : 'Unknown error')
      }
    }, POLL_INTERVAL_MS)
  }, [])

  // Initial status read (shows "last updated"; adopts an in-flight refresh).
  useEffect(() => {
    mountedRef.current = true
    fetchRefreshStatus()
      .then((s) => {
        if (!mountedRef.current) return
        setStatus(s)
        if (s.state === 'running') {
          setRefreshing(true)
          poll()
        }
      })
      .catch(() => {
        // Status is informational — a failed read must not break the page.
      })
    return () => {
      mountedRef.current = false
      stopPolling()
    }
  }, [poll])

  const refresh = useCallback(() => {
    if (refreshing) return
    setError(null)
    setRefreshing(true)
    triggerRefresh()
      .then((s) => {
        if (!mountedRef.current) return
        setStatus(s)
        poll()
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return
        setRefreshing(false)
        setError(err instanceof Error ? err.message : 'Unknown error')
      })
  }, [refreshing, poll])

  return { refreshing, status, error, refresh }
}
