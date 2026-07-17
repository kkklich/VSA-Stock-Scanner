// Drop-in replacement for useState that persists the value in localStorage,
// so a user's UI choices (scanner parameters, view toggles) survive reloads.
// Safe if localStorage is unavailable (private mode / quota): it silently
// falls back to in-memory state.

import { useEffect, useState } from 'react'

/** Read a persisted value, falling back to `initial` on any error. */
function readStored<T>(key: string, initial: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? initial : (JSON.parse(raw) as T)
  } catch {
    return initial
  }
}

/**
 * Like `useState`, but the value is loaded from and saved to
 * `localStorage[key]`. The key should be a stable, app-unique string
 * (e.g. `stockpilot:volume-surge:params`).
 */
export function usePersistentState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => readStored(key, initial))

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* ignore quota / private-mode errors */
    }
  }, [key, value])

  return [value, setValue] as const
}
