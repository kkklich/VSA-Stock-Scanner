// Data hooks for the System page: health, errors and the action log.
//
// Kept in one file because they are one screen's needs and share the same
// mechanics: poll on an interval, expose a manual reload, and surface a 401
// separately so the page can ask for the admin token instead of showing
// "request failed" over and over.

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import {
  fetchActionLogs,
  fetchErrors,
  fetchSystemHealth,
  type ActionLogQuery,
  type ApiActionLogResponse,
  type ApiErrorList,
  type ApiSystemHealth,
} from '../api/adminApi'

/** How often the health card re-reads by itself. The underlying data changes
 *  once a day (the nightly job), but a run in progress should visibly finish. */
export const HEALTH_POLL_MS = 30_000

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  /** The backend requires an admin token and this browser has none (or a wrong
   *  one). A different problem from a failed request. */
  unauthorized: boolean
  reload: () => void
}

/** Shared machinery: fetch on mount, on `deps` change, and on demand. */
function useAsync<T>(
  load: () => Promise<T>,
  deps: unknown[],
  pollMs = 0,
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [unauthorized, setUnauthorized] = useState(false)
  const [tick, setTick] = useState(0)

  // Keep the newest loader without making it a dependency of the effect: the
  // caller passes an inline arrow, which would otherwise re-fetch every render.
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadRef
      .current()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
        setUnauthorized(false)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setUnauthorized(err instanceof ApiError && err.status === 401)
        setError(err instanceof Error ? err.message : 'Unknown error')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  useEffect(() => {
    if (pollMs <= 0) return
    const id = window.setInterval(() => setTick((t) => t + 1), pollMs)
    return () => window.clearInterval(id)
  }, [pollMs])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, loading, error, unauthorized, reload }
}

/** Did the refresh run, is the data current, what is failing? */
export function useSystemHealth(pollMs = HEALTH_POLL_MS): AsyncState<ApiSystemHealth> {
  return useAsync<ApiSystemHealth>(() => fetchSystemHealth(), [], pollMs)
}

/** Recent errors, grouped by what went wrong.
 *
 *  `refreshToken` is any value that changes when the page wants a refetch —
 *  the health card passes its own `asOf`, so "Check again" and the 30-second
 *  poll refresh the whole screen rather than only the card that owns the
 *  button. */
export function useErrorGroups(
  hours = 24,
  refreshToken?: unknown,
): AsyncState<ApiErrorList> {
  return useAsync<ApiErrorList>(() => fetchErrors(hours), [hours, refreshToken])
}

/** The action log — what the app has been doing. */
export function useActionLogs(
  query: ActionLogQuery,
  refreshToken?: unknown,
): AsyncState<ApiActionLogResponse> {
  const { kind, outcome, action, page, pageSize } = query
  return useAsync<ApiActionLogResponse>(
    () => fetchActionLogs({ kind, outcome, action, page, pageSize }),
    [kind, outcome, action, page, pageSize, refreshToken],
  )
}
