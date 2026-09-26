// "Has the data changed since this page loaded it?" — asked for the whole app.
//
// The backend's data moves on its own: the evening refresh stores each day's
// final bars, and while an exchange is open the hourly live-price run replaces
// today's prices. A page left open would otherwise show 10:00 prices at 15:00.
//
// One watcher serves every page. While at least one component listens (the top
// bar always does), it reads GET /api/stocks/refresh/status once at start, then
// every few minutes while the tab is visible and again the moment the tab comes
// back into view. When the status says the data changed — a new refresh time or
// a new live-price time — it bumps a version number, and the data hooks that
// list it among their dependencies reload quietly: no spinner, and what is on
// screen stays until the new figures arrive.
//
// The same status carries when each market's live prices were downloaded
// today, which the top bar shows as its "last sync" time.

import { useSyncExternalStore } from 'react'
import { fetchRefreshStatus, type ApiRefreshStatus } from '../api/stocksApi'

/** How often an open page asks whether the data changed. */
export const DATA_POLL_MS = 5 * 60_000

interface Snapshot {
  /** Bumped every time the backend's data is seen to change. */
  version: number
  /** Per market, when its live prices were last downloaded today (ISO). */
  liveMarkets: Record<string, string>
}

let snapshot: Snapshot = { version: 0, liveMarkets: {} }
// What the data looked like when last asked; null until the first answer.
let lastKey: string | null = null
let timer: ReturnType<typeof setInterval> | null = null
const listeners = new Set<() => void>()

function publish(next: Snapshot): void {
  snapshot = next
  listeners.forEach((listener) => listener())
}

function keyOf(status: ApiRefreshStatus): string {
  return `${status.lastRefreshAt ?? ''}|${status.livePricesAt ?? ''}`
}

function sameMarkets(a: Record<string, string>, b: Record<string, string>): boolean {
  const keys = Object.keys(a)
  return keys.length === Object.keys(b).length && keys.every((k) => a[k] === b[k])
}

/**
 * Tell the watcher about a refresh status fetched elsewhere. `bump: false` is
 * for a caller that reloads its own data anyway (the Refresh button, when its
 * run finishes), so the page does not reload twice.
 */
export function noteRefreshStatus(
  status: ApiRefreshStatus,
  { bump = true }: { bump?: boolean } = {},
): void {
  const key = keyOf(status)
  const changed = lastKey !== null && key !== lastKey && bump
  lastKey = key
  const liveMarkets = status.liveMarkets ?? {}
  if (changed || !sameMarkets(liveMarkets, snapshot.liveMarkets)) {
    publish({
      version: snapshot.version + (changed ? 1 : 0),
      liveMarkets,
    })
  }
}

/**
 * Ask the backend once. `always` is for the first ask: it is the baseline the
 * page's own data was loaded against, so it must be taken even in a tab that
 * opened in the background — skip it and the first ask on becoming visible
 * would swallow every change made meanwhile. The periodic asks wait while the
 * tab is hidden; the one on becoming visible catches up.
 */
async function poll(always = false): Promise<void> {
  if (!always && typeof document !== 'undefined' && document.visibilityState === 'hidden') {
    return
  }
  try {
    noteRefreshStatus(await fetchRefreshStatus())
  } catch {
    // Informational: a failed read keeps what is on screen, and the next
    // poll tries again.
  }
}

function onVisibilityChange(): void {
  if (document.visibilityState === 'visible') void poll()
}

function start(): void {
  void poll(true)
  timer = setInterval(() => void poll(), DATA_POLL_MS)
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }
}

function stop(): void {
  if (timer !== null) clearInterval(timer)
  timer = null
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityChange)
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  if (listeners.size === 1) start()
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) stop()
  }
}

const getSnapshot = () => snapshot

/** A number that grows every time the backend's data changes. */
export function useDataVersion(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot).version
}

/** Per market id, when today's live prices were last downloaded (ISO). */
export function useLiveMarketTimes(): Record<string, string> {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot).liveMarkets
}

/** Test helper: forget everything seen so far. */
export function resetDataVersionForTests(): void {
  stop()
  listeners.clear()
  lastKey = null
  snapshot = { version: 0, liveMarkets: {} }
}
